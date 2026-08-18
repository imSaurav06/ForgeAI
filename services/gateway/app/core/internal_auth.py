"""
Internal Service Authentication Manager providing HMAC token signing, header injection, and signature verification.
"""

from __future__ import annotations

import hashlib
import hmac
import time

from shared.config.settings import get_settings
from shared.exceptions.handlers import UnauthorizedException
from shared.logging.logger import logger


class InternalAuthManager:
    """Manager providing HMAC-based internal service token generation and validation."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.secret_key = self.settings.internal_service_token.encode("utf-8")

    def generate_internal_token(self, service_name: str = "api-gateway") -> str:
        """Generate time-stamped HMAC token identifying gateway requests to downstream microservices."""
        timestamp = str(int(time.time()))
        msg = f"{service_name}:{timestamp}".encode()
        signature = hmac.new(self.secret_key, msg, hashlib.sha256).hexdigest()
        return f"{service_name}:{timestamp}:{signature}"

    def verify_internal_token(self, token: str | None, max_age_seconds: int = 300) -> bool:
        """Verify internal service token timestamp and HMAC signature."""
        if not token or ":" not in token:
            return False

        parts = token.split(":")
        if len(parts) != 3:
            # Fallback for simple legacy token format service_name:signature
            if len(parts) == 2:
                service_name, signature = parts
                msg = service_name.encode("utf-8")
                expected_sig = hmac.new(self.secret_key, msg, hashlib.sha256).hexdigest()
                return hmac.compare_digest(signature, expected_sig)
            return False

        service_name, timestamp_str, signature = parts
        try:
            timestamp = int(timestamp_str)
            now = int(time.time())
            if abs(now - timestamp) > max_age_seconds:
                logger.warning(f"Internal token timestamp drift exceeded limit ({now - timestamp}s)")
                return False
        except ValueError:
            return False

        msg = f"{service_name}:{timestamp_str}".encode()
        expected_sig = hmac.new(self.secret_key, msg, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected_sig)

    def inject_internal_headers(
        self,
        headers: dict[str, str],
        user_id: str = "user_dev_local",
        user_role: str = "developer",
    ) -> dict[str, str]:
        """Inject internal authentication and user identity headers into downstream proxy headers."""
        headers["X-Internal-Service-Token"] = self.generate_internal_token()
        headers["X-User-ID"] = user_id
        headers["X-User-Role"] = user_role
        return headers


def verify_internal_service_request(token: str | None) -> None:
    """Raise UnauthorizedException if internal token is invalid or missing."""
    manager = InternalAuthManager()
    if not manager.verify_internal_token(token):
        raise UnauthorizedException(message="Invalid or missing internal service authorization token")
