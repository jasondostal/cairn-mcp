"""Minimal OIDC client for Authorization Code flow with PKCE.

Supports any OIDC-compliant provider (Authentik, Keycloak, Auth0, etc.).
Uses stdlib urllib for HTTP to avoid adding new dependencies.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)

# PyJWT for ID token validation via JWKS
try:
    import jwt
    from jwt import PyJWKClient
    _JWT_AVAILABLE = True
except ImportError:
    _JWT_AVAILABLE = False


@dataclass
class OIDCClient:
    """OIDC client implementing Authorization Code flow with PKCE."""

    provider_url: str
    client_id: str
    client_secret: str
    scopes: str = "openid email profile"

    # Cached discovery document and JWKS client
    _discovery: dict | None = field(default=None, repr=False)
    _jwks_client: Any = field(default=None, repr=False)
    _lock: Lock = field(default_factory=Lock, repr=False)

    def discovery(self) -> dict:
        """Fetch and cache the OIDC discovery document."""
        if self._discovery is not None:
            return self._discovery
        with self._lock:
            if self._discovery is not None:
                return self._discovery
            url = f"{self.provider_url.rstrip('/')}/.well-known/openid-configuration"
            logger.info("Fetching OIDC discovery from %s", url)
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                self._discovery = json.loads(resp.read())
            return self._discovery

    def _get_jwks_client(self) -> PyJWKClient:
        """Get or create a cached PyJWKClient."""
        if self._jwks_client is not None:
            return self._jwks_client
        if not _JWT_AVAILABLE:
            raise RuntimeError("pyjwt[cryptography] is required for OIDC")
        disc = self.discovery()
        self._jwks_client = PyJWKClient(disc["jwks_uri"])
        return self._jwks_client

    def authorization_url(self, redirect_uri: str, state: str, code_verifier: str) -> str:
        """Build the authorization redirect URL with PKCE."""
        disc = self.discovery()
        code_challenge = (
            base64.urlsafe_b64encode(
                hashlib.sha256(code_verifier.encode()).digest()
            )
            .rstrip(b"=")
            .decode()
        )

        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "scope": self.scopes,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        qs = urllib.parse.urlencode(params)
        return f"{disc['authorization_endpoint']}?{qs}"

    def exchange_code(self, code: str, redirect_uri: str, code_verifier: str) -> dict:
        """Exchange an authorization code for tokens."""
        disc = self.discovery()
        data = urllib.parse.urlencode({
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code_verifier": code_verifier,
        }).encode()

        req = urllib.request.Request(
            disc["token_endpoint"],
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())

    def validate_id_token(self, id_token: str) -> dict:
        """Validate and decode the ID token using JWKS."""
        if not _JWT_AVAILABLE:
            raise RuntimeError("pyjwt[cryptography] is required for OIDC")
        jwks_client = self._get_jwks_client()
        signing_key = jwks_client.get_signing_key_from_jwt(id_token)
        return jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience=self.client_id,
        )


# ---------------------------------------------------------------------------
# OIDC state store — in-memory with TTL for PKCE verifiers
# ---------------------------------------------------------------------------

class OIDCStateStore:
    """In-memory store for OIDC state → code_verifier mapping.

    Single-process safe. For multi-worker deployments, replace with
    Redis or a DB table.
    """

    def __init__(self, ttl_seconds: int = 300):
        # state → (code_verifier, ui_origin, timestamp)
        self._store: dict[str, tuple[str, str, float]] = {}
        self._ttl = ttl_seconds
        self._lock = Lock()

    def create(self, ui_origin: str = "") -> tuple[str, str]:
        """Generate a new (state, code_verifier) pair and store it."""
        state = secrets.token_urlsafe(32)
        code_verifier = secrets.token_urlsafe(64)
        with self._lock:
            self._cleanup()
            self._store[state] = (code_verifier, ui_origin, time.time())
        return state, code_verifier

    def consume(self, state: str) -> tuple[str, str] | None:
        """Retrieve and delete (code_verifier, ui_origin) for a state.

        Returns None if expired/missing.
        """
        with self._lock:
            self._cleanup()
            entry = self._store.pop(state, None)
        if entry is None:
            return None
        code_verifier, ui_origin, _created = entry
        return code_verifier, ui_origin

    def _cleanup(self) -> None:
        """Remove expired entries."""
        now = time.time()
        expired = [k for k, (_, _, t) in self._store.items() if now - t > self._ttl]
        for k in expired:
            del self._store[k]


class OIDCCodeStore:
    """One-time code store for secure OIDC token exchange.

    Instead of passing JWT tokens in redirect URL query parameters (which
    leak into server logs, browser history, and Referer headers), the callback
    stores the JWT under a short-lived random code. The UI exchanges the code
    for the JWT via POST.
    """

    def __init__(self, ttl_seconds: int = 60):
        # code → (jwt_token, username, role, timestamp)
        self._store: dict[str, tuple[str, str, str, float]] = {}
        self._ttl = ttl_seconds
        self._lock = Lock()

    def create(self, token: str, username: str, role: str) -> str:
        """Store a JWT under a one-time code. Returns the code."""
        code = secrets.token_urlsafe(32)
        with self._lock:
            self._cleanup()
            self._store[code] = (token, username, role, time.time())
        return code

    def consume(self, code: str) -> tuple[str, str, str] | None:
        """Retrieve and delete (token, username, role) for a code.

        Returns None if expired/missing.
        """
        with self._lock:
            self._cleanup()
            entry = self._store.pop(code, None)
        if entry is None:
            return None
        token, username, role, _created = entry
        return token, username, role

    def _cleanup(self) -> None:
        """Remove expired entries."""
        now = time.time()
        expired = [k for k, (_, _, _, t) in self._store.items() if now - t > self._ttl]
        for k in expired:
            del self._store[k]
