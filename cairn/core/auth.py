"""Unified authentication — resolves tokens to UserContext.

All transport middleware (REST, MCP HTTP) delegates to this module.
Supports: Cairn JWT, Personal Access Tokens (PATs), legacy API key.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cairn.core.user import UserContext, UserManager

logger = logging.getLogger(__name__)


def resolve_bearer_token(
    token: str,
    *,
    jwt_secret: str,
    user_manager: UserManager,
) -> UserContext | None:
    """Resolve a Bearer token (JWT or PAT) to a UserContext.

    Tries JWT first, then PAT.  Returns UserContext on success, None on failure.
    """
    from cairn.core.user import decode_access_token

    # --- Cairn JWT ---
    payload = decode_access_token(token, secret=jwt_secret)
    if payload:
        try:
            user_id = int(payload["sub"])
        except (KeyError, ValueError):
            return None
        return user_manager.load_user_context(user_id)

    # --- Personal Access Token (PAT) ---
    ctx = user_manager.resolve_api_token(token)
    if ctx:
        return ctx

    return None
