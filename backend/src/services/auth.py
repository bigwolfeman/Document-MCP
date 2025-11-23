"""Authentication helpers (JWT + HF OAuth placeholder)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import jwt
from fastapi import status

from ..models.auth import JWTPayload
from .config import AppConfig, get_config


class AuthError(Exception):
    """Domain-specific authentication error."""

    def __init__(
        self,
        error: str,
        message: str,
        *,
        status_code: int = status.HTTP_401_UNAUTHORIZED,
        detail: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.error = error
        self.message = message
        self.status_code = status_code
        self.detail = detail or {}


class AuthService:
    """Issue and validate JWT tokens (HF OAuth placeholder)."""

    def __init__(
        self,
        config: AppConfig | None = None,
        *,
        algorithm: str = "HS256",
        token_ttl_days: int = 90,
    ) -> None:
        self.config = config or get_config()
        self.algorithm = algorithm
        self.token_ttl_days = token_ttl_days

    @property
    def _local_mode_enabled(self) -> bool:
        return bool(self.config.enable_local_mode)

    @property
    def _local_dev_token(self) -> Optional[str]:
        token = self.config.local_dev_token
        return token.strip() if token else None

    def _require_secret(self) -> str:
        secret = self.config.jwt_secret_key
        if not secret:
            if self._local_mode_enabled and self._local_dev_token:
                # Local mode can operate without JWT secret for read-only flows.
                raise AuthError(
                    "missing_jwt_secret",
                    "JWT secret is not configured; set JWT_SECRET_KEY to enable JWT issuance",
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
            raise AuthError(
                "missing_jwt_secret",
                "JWT secret is not configured; set JWT_SECRET_KEY to enable authentication features",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return secret

    def _build_payload(
        self, user_id: str, expires_in: Optional[timedelta] = None
    ) -> JWTPayload:
        now = datetime.now(timezone.utc)
        lifetime = expires_in or timedelta(days=self.token_ttl_days)
        return JWTPayload(
            sub=user_id,
            iat=int(now.timestamp()),
            exp=int((now + lifetime).timestamp()),
        )

    def _local_dev_payload(self) -> JWTPayload:
        now = datetime.now(timezone.utc)
        return JWTPayload(
            sub="local-dev",
            iat=int(now.timestamp()),
            exp=int((now + timedelta(days=365)).timestamp()),
        )

    def create_jwt(self, user_id: str, *, expires_in: Optional[timedelta] = None) -> str:
        """Create a signed JWT for the given user."""
        payload = self._build_payload(user_id, expires_in)
        return jwt.encode(
            payload.model_dump(),
            self._require_secret(),
            algorithm=self.algorithm,
        )

    def validate_jwt(self, token: str) -> JWTPayload:
        """Validate a JWT and return the decoded payload."""
        if self._local_mode_enabled and self._local_dev_token:
            if token == self._local_dev_token:
                return self._local_dev_payload()
        try:
            decoded = jwt.decode(
                token,
                self._require_secret(),
                algorithms=[self.algorithm],
            )
            return JWTPayload(**decoded)
        except jwt.ExpiredSignatureError as exc:
            raise AuthError("token_expired", "Token expired, please re-authenticate") from exc
        except jwt.InvalidTokenError as exc:
            raise AuthError("invalid_token", f"Invalid token: {exc}") from exc

    def issue_token_response(
        self, user_id: str, *, expires_in: Optional[timedelta] = None
    ) -> tuple[str, datetime]:
        """Return token string and expiry timestamp (helper for API routes)."""
        payload = self._build_payload(user_id, expires_in)
        token = jwt.encode(
            payload.model_dump(),
            self._require_secret(),
            algorithm=self.algorithm,
        )
        expires_at = datetime.fromtimestamp(payload.exp, tz=timezone.utc)
        return token, expires_at

    def exchange_hf_oauth_code(self, code: str) -> Dict[str, Any]:
        """Placeholder for Hugging Face OAuth code exchange."""
        raise NotImplementedError("HF OAuth integration not implemented yet")


__all__ = ["AuthService", "AuthError"]
