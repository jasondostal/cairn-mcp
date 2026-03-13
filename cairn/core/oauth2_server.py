"""OAuth2 Authorization Server for MCP remote clients (e.g. Claude.ai).

Implements the OAuthAuthorizationServerProvider protocol from the MCP SDK.
Delegates user authentication to Authentik via the existing OIDCClient,
then issues Cairn JWTs for MCP access.

Flow:
    Claude.ai -> /authorize -> redirect to Authentik -> user login ->
    /oauth/callback -> generate auth code -> redirect to Claude.ai callback ->
    /token -> issue Cairn JWT + refresh token
"""

from __future__ import annotations

import json
import logging
import secrets
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import TYPE_CHECKING

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    RefreshToken,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

if TYPE_CHECKING:
    from cairn.config import AuthConfig, MCPOAuthConfig, OIDCConfig
    from cairn.core.user import UserManager
    from cairn.storage.database import Database

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Extended types — add user_id to AuthorizationCode for token issuance
# ---------------------------------------------------------------------------

class CairnAuthorizationCode(AuthorizationCode):
    """AuthorizationCode with user_id from Authentik login."""
    user_id: int


class CairnRefreshToken(RefreshToken):
    """RefreshToken with user_id for re-issuing access tokens."""
    user_id: int


# ---------------------------------------------------------------------------
# In-memory stores (single-worker, TTL-based cleanup)
# ---------------------------------------------------------------------------

@dataclass
class PendingAuth:
    """State stored between /authorize and /oauth/callback."""
    client_id: str
    params: AuthorizationParams  # Claude's original auth params (state, redirect_uri, code_challenge)
    code_verifier: str           # PKCE verifier for the Authentik leg
    created_at: float = field(default_factory=time.time)


class PendingAuthStore:
    """Maps cairn_state -> PendingAuth for the Authentik redirect round-trip."""

    def __init__(self, ttl: int = 600):
        self._store: dict[str, PendingAuth] = {}
        self._ttl = ttl
        self._lock = Lock()

    def create(self, client_id: str, params: AuthorizationParams, code_verifier: str) -> str:
        state = secrets.token_urlsafe(32)
        with self._lock:
            self._cleanup()
            self._store[state] = PendingAuth(
                client_id=client_id, params=params, code_verifier=code_verifier,
            )
        return state

    def consume(self, state: str) -> PendingAuth | None:
        with self._lock:
            self._cleanup()
            return self._store.pop(state, None)

    def _cleanup(self) -> None:
        now = time.time()
        expired = [k for k, v in self._store.items() if now - v.created_at > self._ttl]
        for k in expired:
            del self._store[k]


class AuthCodeStore:
    """Maps auth_code -> CairnAuthorizationCode (short-lived, in-memory)."""

    def __init__(self, ttl: int = 300):
        self._store: dict[str, CairnAuthorizationCode] = {}
        self._ttl = ttl
        self._lock = Lock()

    def store(self, code: CairnAuthorizationCode) -> None:
        with self._lock:
            self._cleanup()
            self._store[code.code] = code

    def get(self, code: str) -> CairnAuthorizationCode | None:
        with self._lock:
            self._cleanup()
            return self._store.get(code)

    def consume(self, code: str) -> CairnAuthorizationCode | None:
        with self._lock:
            self._cleanup()
            return self._store.pop(code, None)

    def _cleanup(self) -> None:
        now = time.time()
        expired = [k for k, v in self._store.items() if v.expires_at < now]
        for k in expired:
            del self._store[k]


# ---------------------------------------------------------------------------
# CairnOAuthProvider — implements OAuthAuthorizationServerProvider
# ---------------------------------------------------------------------------

class CairnOAuthProvider:
    """OAuth2 Authorization Server that delegates user auth to Authentik."""

    def __init__(
        self,
        *,
        db: Database,
        oidc_config: OIDCConfig,
        auth_config: AuthConfig,
        mcp_oauth_config: MCPOAuthConfig,
        public_url: str,
        user_manager: UserManager,
    ):
        self._db = db
        self._oidc_config = oidc_config
        self._auth_config = auth_config
        self._mcp_oauth_config = mcp_oauth_config
        self._public_url = public_url.rstrip("/")
        self._user_manager = user_manager

        # In-memory stores
        self._pending_auth = PendingAuthStore()
        self._auth_codes = AuthCodeStore()

        # Lazy OIDC client (reuses existing impl)
        self._oidc_client = None

    def _get_oidc(self):
        if self._oidc_client is None:
            from cairn.core.oidc import OIDCClient
            self._oidc_client = OIDCClient(
                provider_url=self._oidc_config.provider_url,
                client_id=self._oidc_config.client_id,
                client_secret=self._oidc_config.client_secret,
                scopes=self._oidc_config.scopes,
            )
        return self._oidc_client

    # --- Client management (DB-backed) ---

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        row = self._db.execute_one(
            "SELECT metadata FROM oauth2_clients WHERE client_id = %s", (client_id,),
        )
        if not row:
            return None
        return OAuthClientInformationFull.model_validate(row["metadata"])

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        # Hardening: validate redirect URIs — HTTPS only, no localhost/internal
        if client_info.redirect_uris:
            for uri in client_info.redirect_uris:
                uri_str = str(uri)
                if not uri_str.startswith("https://"):
                    raise ValueError(f"redirect_uri must use HTTPS: {uri_str}")
                # Block obviously internal targets
                from urllib.parse import urlparse
                parsed = urlparse(uri_str)
                if parsed.hostname in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
                    raise ValueError(f"redirect_uri cannot target localhost: {uri_str}")

        # Hardening: cap total registered clients to prevent DCR spam
        _MAX_CLIENTS = 50
        count = self._db.execute_one("SELECT COUNT(*) AS cnt FROM oauth2_clients")
        if count and count["cnt"] >= _MAX_CLIENTS:
            logger.warning("OAuth2 DCR rejected: client limit reached (%d)", _MAX_CLIENTS)
            raise ValueError(f"Maximum number of registered clients ({_MAX_CLIENTS}) reached")

        self._db.execute(
            """INSERT INTO oauth2_clients (client_id, client_secret, client_id_issued_at,
               client_secret_expires_at, metadata) VALUES (%s, %s, %s, %s, %s)""",
            (
                client_info.client_id,
                client_info.client_secret,
                client_info.client_id_issued_at,
                client_info.client_secret_expires_at,
                json.dumps(client_info.model_dump(mode="json")),
            ),
        )
        logger.info("OAuth2 client registered: %s (%s)", client_info.client_id, client_info.client_name)

    # --- Authorization (redirect to Authentik) ---

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        """Return a URL to redirect the user to Authentik for login."""
        oidc = self._get_oidc()

        # Generate PKCE verifier for the Cairn<->Authentik leg
        code_verifier = secrets.token_urlsafe(64)

        # Store the pending auth state so /oauth/callback can resume the flow
        cairn_state = self._pending_auth.create(
            client_id=client.client_id or "",
            params=params,
            code_verifier=code_verifier,
        )

        # Cairn's callback URL — Authentik redirects here after user login
        callback_uri = f"{self._public_url}/oauth/callback"

        # Build Authentik authorization URL
        auth_url = oidc.authorization_url(callback_uri, cairn_state, code_verifier)
        logger.info("OAuth2 authorize: redirecting to Authentik for client %s", client.client_id)
        return auth_url

    # --- Authentik callback handler (Starlette endpoint) ---

    async def callback_handler(self, request: Request) -> Response:
        """Handle redirect back from Authentik after user login.

        Exchanges Authentik auth code for user info, generates a Cairn
        authorization code, and redirects to Claude.ai's callback.
        """
        code = request.query_params.get("code")
        state = request.query_params.get("state")
        error = request.query_params.get("error")

        if error:
            logger.warning("OAuth2 callback: Authentik returned error=%s", error)
            return Response(f"Authentication failed: {error}", status_code=400)

        if not code or not state:
            return Response("Missing code or state parameter", status_code=400)

        # Retrieve pending auth state
        pending = self._pending_auth.consume(state)
        if not pending:
            return Response("Invalid or expired state", status_code=400)

        try:
            oidc = self._get_oidc()
            callback_uri = f"{self._public_url}/oauth/callback"

            # Exchange Authentik code for tokens
            token_response = oidc.exchange_code(code, callback_uri, pending.code_verifier)
            id_token = token_response.get("id_token")
            if not id_token:
                return Response("No id_token in Authentik response", status_code=400)

            # Validate ID token and extract claims
            claims = oidc.validate_id_token(id_token)
            external_id = claims.get("sub")
            if not external_id:
                return Response("No sub claim in ID token", status_code=400)

            # Get or create Cairn user from Authentik claims
            admin_groups = None
            if self._oidc_config.admin_groups:
                admin_groups = [g.strip() for g in self._oidc_config.admin_groups.split(",") if g.strip()]

            user = self._user_manager.get_or_create_oidc_user(
                external_id=external_id,
                claims=claims,
                default_role=self._oidc_config.default_role,
                admin_groups=admin_groups,
            )

            # Sync OIDC group memberships
            oidc_groups = claims.get("groups", [])
            if isinstance(oidc_groups, list) and oidc_groups:
                try:
                    self._user_manager.sync_oidc_groups(user["id"], oidc_groups)
                except Exception:
                    logger.warning("OIDC group sync failed for user %s", user["id"], exc_info=True)

            # Generate Cairn authorization code (>= 160 bits entropy per RFC 6749)
            cairn_code = secrets.token_urlsafe(30)  # 240 bits
            auth_code = CairnAuthorizationCode(
                code=cairn_code,
                scopes=pending.params.scopes or [],
                expires_at=time.time() + 300,
                client_id=pending.client_id,
                code_challenge=pending.params.code_challenge,
                redirect_uri=pending.params.redirect_uri,
                redirect_uri_provided_explicitly=pending.params.redirect_uri_provided_explicitly,
                resource=pending.params.resource,
                user_id=user["id"],
            )
            self._auth_codes.store(auth_code)

            # Redirect to Claude.ai's callback with the auth code
            redirect_url = construct_redirect_uri(
                str(pending.params.redirect_uri),
                code=cairn_code,
                state=pending.params.state,
            )
            logger.info(
                "OAuth2 callback: user=%s, client=%s, redirecting to client callback",
                user["username"], pending.client_id,
            )
            return RedirectResponse(url=redirect_url, status_code=302)

        except Exception:
            logger.exception("OAuth2 callback failed")
            return Response("Authentication failed", status_code=500)

    # --- Authorization code exchange ---

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str,
    ) -> CairnAuthorizationCode | None:
        return self._auth_codes.get(authorization_code)

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: CairnAuthorizationCode,
    ) -> OAuthToken:
        # Consume the code (one-time use)
        self._auth_codes.consume(authorization_code.code)

        # Issue Cairn JWT access token
        from cairn.core.user import create_access_token
        user = self._user_manager.get_by_id(authorization_code.user_id)
        if not user:
            from mcp.server.auth.provider import TokenError
            raise TokenError(error="invalid_grant", error_description="User not found")

        access_token = create_access_token(
            user["id"], user["username"], user["role"],
            secret=self._auth_config.jwt_secret,
            expire_minutes=self._mcp_oauth_config.access_token_expiry // 60,
        )

        # Issue refresh token (DB-backed)
        refresh_token = secrets.token_urlsafe(48)
        scopes = authorization_code.scopes or []
        expires_at = int(time.time()) + self._mcp_oauth_config.refresh_token_expiry

        self._db.execute(
            """INSERT INTO oauth2_refresh_tokens (token, client_id, user_id, scopes, expires_at)
               VALUES (%s, %s, %s, %s, %s)""",
            (refresh_token, client.client_id, authorization_code.user_id, scopes, expires_at),
        )

        logger.info("OAuth2 token issued for user=%s client=%s", user["username"], client.client_id)
        return OAuthToken(
            access_token=access_token,
            token_type="Bearer",
            expires_in=self._mcp_oauth_config.access_token_expiry,
            scope=" ".join(scopes) if scopes else None,
            refresh_token=refresh_token,
        )

    # --- Refresh token exchange ---

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str,
    ) -> CairnRefreshToken | None:
        row = self._db.execute_one(
            """SELECT token, client_id, user_id, scopes, expires_at
               FROM oauth2_refresh_tokens WHERE token = %s""",
            (refresh_token,),
        )
        if not row:
            return None
        # Hardening: reject expired refresh tokens
        if row["expires_at"] and row["expires_at"] < int(time.time()):
            self._db.execute("DELETE FROM oauth2_refresh_tokens WHERE token = %s", (refresh_token,))
            logger.info("OAuth2 expired refresh token cleaned up for client=%s", row["client_id"])
            return None
        return CairnRefreshToken(
            token=row["token"],
            client_id=row["client_id"],
            user_id=row["user_id"],
            scopes=row["scopes"] or [],
            expires_at=row["expires_at"],
        )

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: CairnRefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        from mcp.server.auth.provider import TokenError

        from cairn.core.user import create_access_token

        user = self._user_manager.get_by_id(refresh_token.user_id)
        if not user:
            raise TokenError(error="invalid_grant", error_description="User not found")

        # Issue new access token
        access_token = create_access_token(
            user["id"], user["username"], user["role"],
            secret=self._auth_config.jwt_secret,
            expire_minutes=self._mcp_oauth_config.access_token_expiry // 60,
        )

        # Rotate refresh token: delete old, create new
        new_refresh = secrets.token_urlsafe(48)
        expires_at = int(time.time()) + self._mcp_oauth_config.refresh_token_expiry

        self._db.execute("DELETE FROM oauth2_refresh_tokens WHERE token = %s", (refresh_token.token,))
        self._db.execute(
            """INSERT INTO oauth2_refresh_tokens (token, client_id, user_id, scopes, expires_at)
               VALUES (%s, %s, %s, %s, %s)""",
            (new_refresh, client.client_id, refresh_token.user_id, scopes, expires_at),
        )

        logger.info("OAuth2 token refreshed for user=%s client=%s", user["username"], client.client_id)
        return OAuthToken(
            access_token=access_token,
            token_type="Bearer",
            expires_in=self._mcp_oauth_config.access_token_expiry,
            scope=" ".join(scopes) if scopes else None,
            refresh_token=new_refresh,
        )

    # --- Access token verification ---

    async def load_access_token(self, token: str) -> AccessToken | None:
        """Verify a Cairn JWT and return AccessToken for the SDK's auth middleware."""
        from cairn.core.user import decode_access_token, set_user

        payload = decode_access_token(token, secret=self._auth_config.jwt_secret)
        if payload:
            try:
                user_id = int(payload["sub"])
            except (KeyError, ValueError):
                return None
            ctx = self._user_manager.load_user_context(user_id)
            if ctx:
                set_user(ctx)
                return AccessToken(
                    token=token,
                    client_id=payload.get("client_id", "cairn"),
                    scopes=payload.get("scopes", []),
                    expires_at=payload.get("exp"),
                )
            return None

        # Try PAT resolution
        ctx = self._user_manager.resolve_api_token(token)
        if ctx:
            set_user(ctx)
            return AccessToken(
                token=token,
                client_id="pat",
                scopes=[],
            )

        return None

    # --- Token revocation ---

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        if isinstance(token, RefreshToken):
            self._db.execute(
                "DELETE FROM oauth2_refresh_tokens WHERE token = %s", (token.token,),
            )
            logger.info("OAuth2 refresh token revoked for client=%s", token.client_id)

    # --- Maintenance ---

    def cleanup_expired_tokens(self) -> int:
        """Delete expired refresh tokens. Returns count of deleted rows."""
        now = int(time.time())
        result = self._db.execute(
            "DELETE FROM oauth2_refresh_tokens WHERE expires_at IS NOT NULL AND expires_at < %s",
            (now,),
        )
        count = result if isinstance(result, int) else 0
        if count:
            logger.info("OAuth2 cleanup: deleted %d expired refresh tokens", count)
        return count
