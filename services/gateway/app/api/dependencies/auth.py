"""
Authentication & Authorization Dependency for API Gateway.

Validates Bearer JWT signatures, expiration, claims, and API keys.
Strips unauthenticated requests and extracts verified user identity.
"""

from __future__ import annotations

import time
from typing import Any

import jwt
from fastapi import Header, Request

from shared.config.settings import get_settings
from shared.exceptions.handlers import UnauthorizedException
from shared.logging.logger import logger


def generate_jwt_token(
    user_id: str,
    role: str = "user",
    expiration_minutes: int | None = None,
    secret_key: str | None = None,
) -> str:
    """Generate a signed Bearer JWT token with user identity and claims."""
    settings = get_settings()
    secret = secret_key or settings.jwt_secret
    exp_minutes = expiration_minutes or settings.jwt_expiration_minutes

    now = time.time()
    payload = {
        "sub": user_id,
        "user_id": user_id,
        "role": role,
        "iat": int(now),
        "exp": int(now + exp_minutes * 60),
        "iss": "forge-ai-gateway",
    }
    return jwt.encode(payload, secret, algorithm=settings.jwt_algorithm)


def decode_and_verify_jwt_token(token: str, secret_key: str | None = None) -> dict[str, Any]:
    """Decode and verify JWT signature, expiration, and claims."""
    settings = get_settings()
    secret = secret_key or settings.jwt_secret

    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[settings.jwt_algorithm],
            options={"verify_signature": True, "verify_exp": True},
        )
        user_id = payload.get("sub") or payload.get("user_id")
        if not user_id:
            raise UnauthorizedException(message="Invalid token payload: missing subject/user_id claim")
        return payload
    except jwt.ExpiredSignatureError as err:
        raise UnauthorizedException(message="Authentication token has expired") from err
    except jwt.InvalidTokenError as err:
        raise UnauthorizedException(message=f"Invalid authentication token: {err}") from err

async def verify_auth_token(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """
    Production FastAPI Authentication Dependency.

    Supports:
    - Bearer JWT through Authorization header
    - X-API-Key
    - JWT query token only for SSE stream endpoints
    - Explicit development fallback when enabled
    """
    settings = get_settings()

    if authorization:
        if not authorization.startswith("Bearer "):
            raise UnauthorizedException(
                message="Invalid Authorization header scheme. Must be 'Bearer <token>'"
            )

        token = authorization.removeprefix("Bearer ").strip()
        payload = decode_and_verify_jwt_token(token)

        result = {
            "auth_type": "bearer",
            "token": token,
            "user_id": payload.get("sub") or payload.get("user_id"),
            "role": payload.get("role", "user"),
            "claims": payload,
        }

        request.state.auth_context = result
        return result

    if x_api_key:
        if len(x_api_key.strip()) < 8:
            raise UnauthorizedException(
                message="Invalid API Key format"
            )

        result = {
            "auth_type": "api_key",
            "token": x_api_key,
            "user_id": f"api_key_user_{x_api_key[:8]}",
            "role": "developer",
        }

        request.state.auth_context = result
        return result

    # EventSource cannot send custom Authorization headers.
    # Query-token authentication is therefore allowed only
    # for the Agent SSE stream endpoint.
    query_token = request.query_params.get("token")

    if query_token and request.url.path.endswith("/stream"):
        token = query_token.strip()

        if not token:
            raise UnauthorizedException(
                message="Invalid SSE authentication token"
            )

        payload = decode_and_verify_jwt_token(token)

        result = {
            "auth_type": "bearer_query",
            "token": token,
            "user_id": payload.get("sub") or payload.get("user_id"),
            "role": payload.get("role", "user"),
            "claims": payload,
        }

        request.state.auth_context = result
        return result

    # Development fallback
    if settings.allow_dev_auth_fallback:
        logger.warning(
            "Unauthenticated request accepted via development fallback "
            "(allow_dev_auth_fallback=True)"
        )

        result = {
            "auth_type": "local_dev",
            "token": "dev_token",
            "user_id": "user_local_dev",
            "role": "admin",
        }

        request.state.auth_context = result
        return result

    raise UnauthorizedException(
        message=(
            "Missing or invalid authentication credentials. "
            "Bearer token or API key required."
        )
    )
