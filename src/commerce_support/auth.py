from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time


class AuthenticationError(Exception):
    pass


class TokenService:
    def __init__(self, secret: str, ttl_seconds: int = 3600) -> None:
        self.secret = secret.encode()
        self.ttl_seconds = ttl_seconds
        self._sessions: dict[str, tuple[str, int]] = {}
        self._lock = threading.Lock()

    def issue(self, user_id: str) -> str:
        nonce = secrets.token_urlsafe(24)
        expires_at = int(time.time()) + self.ttl_seconds
        with self._lock:
            self._sessions[nonce] = (user_id, expires_at)
        signature = hmac.new(self.secret, nonce.encode(), hashlib.sha256).hexdigest()
        return f"{nonce}.{signature}"

    def verify(self, token: str) -> str:
        try:
            nonce, signature = token.split(".", 1)
            expected = hmac.new(self.secret, nonce.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, signature):
                raise AuthenticationError("invalid_token")
            with self._lock:
                session = self._sessions.get(nonce)
            if session is None:
                raise AuthenticationError("invalid_token")
            user_id, expires_at = session
            if expires_at < int(time.time()):
                with self._lock:
                    self._sessions.pop(nonce, None)
                raise AuthenticationError("invalid_token")
            return user_id
        except AuthenticationError:
            raise
        except Exception as error:
            raise AuthenticationError("invalid_token") from error
