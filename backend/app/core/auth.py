"""
ASTRA OS — Local Session Auth
==============================
Single-user local desktop app. No multi-tenant. No JWT.

Architecture:
  - One local session token stored in `local_session.json` next to the DB.
  - Token is a 64-char hex secret generated on first launch.
  - All protected routes use `get_local_session` dependency.
  - No password hashing, no bcrypt, no JOSE — removed entirely.

Migration from JWT:
  - `get_current_user` is replaced by `get_local_session` which returns
    a fixed LocalUser object. All routes that depended on `get_current_user`
    can replace the import with `get_local_session` drop-in.
  - The `/api/v1/auth` router now exposes: /status, /token (get), /reset-token.
"""

import os
import json
import secrets
import logging
from pathlib import Path
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ── Token storage ─────────────────────────────────────────────────────────────
# Stored adjacent to the SQLite DB file, never in the repo.
_TOKEN_FILE = Path(os.getenv("SESSION_TOKEN_PATH", "local_session.json"))
_TOKEN_LENGTH = 64  # 256-bit hex token


def _load_or_create_token() -> str:
    """Load existing local token or generate a new one on first launch."""
    if _TOKEN_FILE.exists():
        try:
            data = json.loads(_TOKEN_FILE.read_text())
            token = data.get("token", "")
            if len(token) == _TOKEN_LENGTH:
                return token
        except Exception:
            pass  # Corrupted file — regenerate

    token = secrets.token_hex(_TOKEN_LENGTH // 2)  # hex chars = bytes * 2
    _TOKEN_FILE.write_text(json.dumps({"token": token}, indent=2))
    try:
        _TOKEN_FILE.chmod(0o600)  # owner read/write only (Unix)
    except OSError:
        pass  # Windows: chmod not supported — ACL handles permissions
    logger.info(f"🔑 New local session token generated → {_TOKEN_FILE}")
    return token


# Module-level singleton — loaded once at import time
_LOCAL_TOKEN: str = _load_or_create_token()


# ── User model ────────────────────────────────────────────────────────────────

class LocalUser(BaseModel):
    """Single local user. No DB lookup required."""
    id: str = "local"
    name: str = "Local User"
    is_active: bool = True
    is_local: bool = True


_LOCAL_USER = LocalUser()


# ── FastAPI dependency ────────────────────────────────────────────────────────

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_local_session(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> LocalUser:
    """
    Validate the local session token.

    Replaces JWT `get_current_user` as a drop-in dependency.
    Returns the fixed LocalUser on success, raises 401 on failure.

    Frontend: send `Authorization: Bearer <token>` header.
    Token is retrieved once from GET /api/v1/auth/token.
    """
    if credentials is None or credentials.credentials != _LOCAL_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing local session token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _LOCAL_USER


def get_local_token() -> str:
    """Return the current local session token (for the /token endpoint)."""
    return _LOCAL_TOKEN


def reset_local_token() -> str:
    """Generate a new token and persist it. Invalidates all existing sessions."""
    global _LOCAL_TOKEN
    _LOCAL_TOKEN = secrets.token_hex(_TOKEN_LENGTH // 2)
    _TOKEN_FILE.write_text(json.dumps({"token": _LOCAL_TOKEN}, indent=2))
    try:
        _TOKEN_FILE.chmod(0o600)
    except OSError:
        pass  # Windows: chmod not supported
    logger.warning("⚠️  Local session token was reset. All existing sessions are now invalid.")
    return _LOCAL_TOKEN
