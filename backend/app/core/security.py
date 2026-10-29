"""JWT authentication and RBAC helpers."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_config

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12, bcrypt__ident="2b")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)

# Role hierarchy
ROLES = ("operator", "engineer", "expert", "approver", "admin", "auditor")
ROLE_LEVEL = {r: i for i, r in enumerate(ROLES)}


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict[str, Any], expires_minutes: int | None = None) -> str:
    cfg = get_config()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or cfg.settings.jwt_expire_minutes
    )
    payload = {**data, "exp": expire}
    return jwt.encode(payload, cfg.settings.jwt_secret_key, algorithm=cfg.settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    cfg = get_config()
    return jwt.decode(token, cfg.settings.jwt_secret_key, algorithms=[cfg.settings.jwt_algorithm])


async def get_current_user(token: str | None = Depends(oauth2_scheme)) -> dict[str, Any]:
    """Extract and validate the current user from JWT token."""
    if not token:
        # Allow unauthenticated in mock/dev mode
        cfg = get_config()
        if cfg.is_mock:
            return {"sub": "dev-user", "role": "admin", "name": "Dev User"}
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    try:
        payload = decode_token(token)
        return payload
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


def require_role(*roles: str):
    """Dependency factory: require the current user to have one of the given roles."""
    async def _check(user: dict = Depends(get_current_user)) -> dict:
        user_role = user.get("role", "operator")
        if user_role not in roles and user_role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user_role}' is not allowed. Required: {roles}",
            )
        return user
    return _check
