from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time


class AuthenticationError(Exception):
    pass


class TokenService:
    def __init__(self, secret: str, ttl_seconds: int = 3600) -> None:
        self.secret = secret.encode()
        self.ttl_seconds = ttl_seconds

    def issue(self, user_id: str) -> str:
        payload = json.dumps(
            {"sub": user_id, "exp": int(time.time()) + self.ttl_seconds}, separators=(",", ":")
        ).encode()
        body = base64.urlsafe_b64encode(payload).rstrip(b"=")
        signature = hmac.new(self.secret, body, hashlib.sha256).digest()
        return (body + b"." + base64.urlsafe_b64encode(signature).rstrip(b"=")).decode()

    def verify(self, token: str) -> str:
        try:
            body, signature = token.encode().split(b".", 1)
            expected = hmac.new(self.secret, body, hashlib.sha256).digest()
            actual = base64.urlsafe_b64decode(signature + b"=" * (-len(signature) % 4))
            if not hmac.compare_digest(expected, actual):
                raise AuthenticationError("invalid_token")
            payload = json.loads(base64.urlsafe_b64decode(body + b"=" * (-len(body) % 4)))
            if payload["exp"] < int(time.time()):
                raise AuthenticationError("invalid_token")
            return str(payload["sub"])
        except AuthenticationError:
            raise
        except Exception as error:
            raise AuthenticationError("invalid_token") from error
