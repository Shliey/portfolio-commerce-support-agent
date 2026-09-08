import pytest

from commerce_support.observability import (
    ToolExecutionFailed,
    ToolExecutor,
    ToolLimitExceeded,
)


def test_tool_log_masks_secrets_and_records_context() -> None:
    entries: list[dict[str, object]] = []
    executor = ToolExecutor(
        context={"run_id": "run-1", "user_id": "user-1", "thread_id": "thread-1"},
        sink=entries.append,
    )
    assert executor.call("lookup", lambda: 42, {"token": "secret-token", "query": "safe"}) == 42
    assert entries[0]["run_id"] == "run-1"
    assert entries[0]["duration_ms"] >= 0  # type: ignore[operator]
    assert entries[0]["inputs"] == {"token": "[REDACTED]", "query": "safe"}
    assert "secret-token" not in str(entries)


def test_transient_tool_failure_has_bounded_exponential_retry() -> None:
    sleeps: list[float] = []
    attempts = 0

    def flaky() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise TimeoutError
        return "ok"

    executor = ToolExecutor(context={}, max_attempts=3, backoff_seconds=0.5, sleep=sleeps.append)
    assert executor.call("flaky", flaky, {}) == "ok"
    assert sleeps == [0.5, 1.0]


def test_persistent_failure_and_tool_limit_are_stable() -> None:
    executor = ToolExecutor(context={}, max_calls=1, max_attempts=1)
    with pytest.raises(ToolExecutionFailed, match="tool_execution_failed"):
        executor.call("broken", lambda: (_ for _ in ()).throw(ConnectionError()), {})
    with pytest.raises(ToolLimitExceeded, match="tool_limit_exceeded"):
        executor.call("extra", lambda: None, {})
