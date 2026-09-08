from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")
SENSITIVE_KEYS = frozenset({"password", "token", "authorization", "api_key", "secret"})


class ToolLimitExceeded(Exception):
    pass


class ToolExecutionFailed(Exception):
    pass


def mask_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if key.lower() in SENSITIVE_KEYS else mask_sensitive(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [mask_sensitive(item) for item in value]
    return value


class ToolExecutor:
    def __init__(
        self,
        *,
        context: dict[str, str],
        sink: Callable[[dict[str, Any]], None] | None = None,
        max_calls: int = 4,
        max_attempts: int = 2,
        backoff_seconds: float = 0.01,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.context = context
        self.sink = sink or self._default_sink
        self.max_calls = max_calls
        self.max_attempts = max_attempts
        self.backoff_seconds = backoff_seconds
        self.sleep = sleep
        self.calls = 0

    @staticmethod
    def _default_sink(entry: dict[str, Any]) -> None:
        logging.getLogger("commerce_support.tools").info("tool_call", extra={"event": entry})

    def call(self, name: str, function: Callable[[], T], inputs: dict[str, Any]) -> T:
        self.calls += 1
        if self.calls > self.max_calls:
            raise ToolLimitExceeded("tool_limit_exceeded")
        started = time.perf_counter()
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                result = function()
                self._record(name, inputs, started, attempt, "success")
                return result
            except (TimeoutError, ConnectionError) as error:
                last_error = error
                if attempt < self.max_attempts:
                    self.sleep(self.backoff_seconds * (2 ** (attempt - 1)))
        self._record(name, inputs, started, self.max_attempts, "failed")
        raise ToolExecutionFailed("tool_execution_failed") from last_error

    def _record(
        self,
        name: str,
        inputs: dict[str, Any],
        started: float,
        attempts: int,
        status: str,
    ) -> None:
        self.sink(
            {
                **self.context,
                "call_type": "tool",
                "name": name,
                "inputs": mask_sensitive(inputs),
                "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                "attempts": attempts,
                "status": status,
            }
        )
