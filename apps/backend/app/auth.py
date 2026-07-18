"""Optional Supabase JWT authentication with a safe local-development mode."""

import asyncio
from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Header, HTTPException, status

from app.config import settings


@lru_cache(maxsize=2)
def _jwks_client(supabase_url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json")


@dataclass(frozen=True)
class CurrentUser:
    """Authenticated application user."""

    user_id: str
    email: str | None = None


async def get_current_user(
    authorization: str | None = Header(default=None),
) -> CurrentUser:
    """Validate a Supabase access token or return the local single-user identity."""
    if not settings.auth_required:
        return CurrentUser(user_id="local-user")

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required."
        )
    if not settings.supabase_jwt_secret and not settings.supabase_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured.",
        )

    token = authorization.removeprefix("Bearer ").strip()
    try:
        if settings.supabase_jwt_secret:
            payload = jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                audience=settings.supabase_jwt_audience,
                options={"require": ["exp", "sub", "aud"]},
            )
        else:
            supabase_url = str(settings.supabase_url).rstrip("/")
            signing_key = await asyncio.to_thread(
                _jwks_client(supabase_url).get_signing_key_from_jwt, token
            )
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["ES256", "RS256"],
                audience=settings.supabase_jwt_audience,
                issuer=f"{supabase_url}/auth/v1",
                options={"require": ["exp", "sub", "aud"]},
            )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session."
        ) from exc

    return CurrentUser(user_id=str(payload["sub"]), email=payload.get("email"))
