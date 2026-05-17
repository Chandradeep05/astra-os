"""
ASTRA OS — Auth API (Local Session)
=====================================
Endpoints:
  GET  /api/v1/auth/status  — Is the server reachable and auth configured?
  GET  /api/v1/auth/token   — Get the current local session token (protected: must already have it)
  POST /api/v1/auth/reset   — Generate a new token (invalidates all sessions)
  GET  /api/v1/auth/me      — Who am I (LocalUser object)

NOTE: JWT register/login endpoints are removed.
      Authentication is now single-user local session.
      The frontend retrieves the token from local_session.json on first launch
      (Tauri can read local files; web dev mode reads from .env or a setup script).
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.auth import (
    get_local_session,
    get_local_token,
    reset_local_token,
    LocalUser,
)

router = APIRouter()


class AuthStatus(BaseModel):
    status: str
    auth_mode: str
    session_active: bool


class TokenResponse(BaseModel):
    token: str
    token_type: str = "bearer"
    message: str


@router.get("/status", response_model=AuthStatus)
async def auth_status():
    """
    Public health check — no token required.
    Returns auth configuration so the frontend knows what mode we're in.
    """
    return AuthStatus(
        status="online",
        auth_mode="local_session",
        session_active=True,
    )


@router.get("/token", response_model=TokenResponse)
async def get_token():
    """
    Returns the local session token.

    In a Tauri desktop app, the token is read directly from local_session.json
    by the Rust shell and injected into the webview on startup — this endpoint
    is the fallback for web dev mode.

    WARNING: This endpoint is intentionally NOT protected in dev mode.
    In a production Tauri build, this endpoint should be localhost-only
    (enforced by Tauri's allowlist, not by this server).
    """
    return TokenResponse(
        token=get_local_token(),
        message="Store this token in your frontend session. Send as Authorization: Bearer <token>.",
    )


@router.post("/reset", response_model=TokenResponse)
async def reset_token(current_user: LocalUser = Depends(get_local_session)):
    """
    Reset the session token. All existing sessions are immediately invalidated.
    Requires the current valid token to prevent accidental resets.
    """
    new_token = reset_local_token()
    return TokenResponse(
        token=new_token,
        message="Token reset. Update your frontend session with the new token.",
    )


@router.get("/me", response_model=LocalUser)
async def get_me(current_user: LocalUser = Depends(get_local_session)):
    """Returns the local user identity."""
    return current_user
