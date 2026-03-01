"""Tests for cairn.core.user — UserContext, JWT, password, PAT, OIDC, and contextvar operations."""

import hashlib
import threading
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, call

from cairn.core.auth import resolve_bearer_token
from cairn.core.user import (
    UserContext,
    set_user,
    current_user,
    clear_user,
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
    UserManager,
)


# ---------------------------------------------------------------------------
# UserContext contextvar tests
# ---------------------------------------------------------------------------

class TestUserContext:
    def test_set_and_get(self):
        clear_user()
        ctx = UserContext(user_id=1, username="alice", role="admin", project_ids=frozenset({1, 2}))
        set_user(ctx)
        assert current_user() is ctx
        assert current_user().username == "alice"
        assert current_user().role == "admin"
        assert current_user().project_ids == frozenset({1, 2})
        clear_user()

    def test_default_is_none(self):
        clear_user()
        assert current_user() is None

    def test_clear_user(self):
        set_user(UserContext(user_id=1, username="bob", role="user"))
        assert current_user() is not None
        clear_user()
        assert current_user() is None

    def test_immutability(self):
        ctx = UserContext(user_id=1, username="test", role="user")
        try:
            ctx.username = "hacked"
            assert False, "Should have raised"
        except AttributeError:
            pass

    def test_thread_isolation(self):
        clear_user()
        set_user(UserContext(user_id=1, username="main", role="admin"))
        result = {}

        def check_in_thread():
            result["user"] = current_user()

        t = threading.Thread(target=check_in_thread)
        t.start()
        t.join()
        assert result["user"] is None
        assert current_user() is not None
        clear_user()

    def test_frozen_project_ids(self):
        ctx = UserContext(user_id=1, username="x", role="user", project_ids=frozenset({10, 20}))
        assert 10 in ctx.project_ids
        assert 30 not in ctx.project_ids

    def test_default_empty_project_ids(self):
        ctx = UserContext(user_id=1, username="x", role="user")
        assert ctx.project_ids == frozenset()


# ---------------------------------------------------------------------------
# Password tests
# ---------------------------------------------------------------------------

class TestPasswordUtils:
    def test_hash_and_verify(self):
        hashed = hash_password("secret123")
        assert hashed != "secret123"
        assert verify_password("secret123", hashed)

    def test_wrong_password(self):
        hashed = hash_password("correct")
        assert not verify_password("wrong", hashed)

    def test_different_hashes(self):
        h1 = hash_password("same")
        h2 = hash_password("same")
        # bcrypt salts differently each time
        assert h1 != h2
        assert verify_password("same", h1)
        assert verify_password("same", h2)


# ---------------------------------------------------------------------------
# JWT tests
# ---------------------------------------------------------------------------

SECRET = "test-secret-key-for-jwt"


class TestJWT:
    def test_encode_decode(self):
        token = create_access_token(42, "alice", "admin", secret=SECRET)
        payload = decode_access_token(token, secret=SECRET)
        assert payload is not None
        assert payload["sub"] == "42"
        assert payload["username"] == "alice"
        assert payload["role"] == "admin"

    def test_expired_token(self):
        token = create_access_token(1, "bob", "user", secret=SECRET, expire_minutes=-1)
        assert decode_access_token(token, secret=SECRET) is None

    def test_invalid_token(self):
        assert decode_access_token("garbage", secret=SECRET) is None

    def test_wrong_secret(self):
        token = create_access_token(1, "x", "user", secret=SECRET)
        assert decode_access_token(token, secret="wrong-secret") is None

    def test_token_is_string(self):
        token = create_access_token(1, "x", "user", secret=SECRET)
        assert isinstance(token, str)
        assert len(token) > 50


# ---------------------------------------------------------------------------
# UserManager tests (with mock DB)
# ---------------------------------------------------------------------------

class TestUserManager:
    def _mock_db(self):
        db = MagicMock()
        db.commit = MagicMock()
        return db

    def test_is_first_user_empty(self):
        db = self._mock_db()
        db.execute_one.return_value = {"cnt": 0}
        mgr = UserManager(db)
        assert mgr.is_first_user()

    def test_is_first_user_has_users(self):
        db = self._mock_db()
        db.execute_one.return_value = {"cnt": 3}
        mgr = UserManager(db)
        assert not mgr.is_first_user()

    def test_get_accessible_project_ids(self):
        db = self._mock_db()
        db.execute.return_value = [
            {"project_id": 1},
            {"project_id": 5},
            {"project_id": 10},
        ]
        mgr = UserManager(db)
        ids = mgr.get_accessible_project_ids(42)
        assert ids == {1, 5, 10}

    def test_get_accessible_project_ids_empty(self):
        db = self._mock_db()
        db.execute.return_value = []
        mgr = UserManager(db)
        ids = mgr.get_accessible_project_ids(42)
        assert ids == set()

    def test_load_user_context(self):
        db = self._mock_db()

        def _execute_one(query, params=None):
            if "FROM users WHERE id" in query:
                return {
                    "id": 1, "username": "alice", "email": "a@b.c",
                    "role": "admin", "is_active": True,
                    "created_at": "2024-01-01", "updated_at": "2024-01-01",
                }
            return None

        db.execute_one.side_effect = _execute_one
        db.execute.return_value = [{"project_id": 10}, {"project_id": 20}]

        mgr = UserManager(db)
        ctx = mgr.load_user_context(1)
        assert ctx is not None
        assert ctx.user_id == 1
        assert ctx.username == "alice"
        assert ctx.role == "admin"
        assert ctx.project_ids == frozenset({10, 20})

    def test_load_user_context_inactive(self):
        db = self._mock_db()
        db.execute_one.return_value = {
            "id": 1, "username": "bob", "email": None,
            "role": "user", "is_active": False,
            "created_at": "2024-01-01", "updated_at": "2024-01-01",
        }
        mgr = UserManager(db)
        ctx = mgr.load_user_context(1)
        assert ctx is None

    def test_load_user_context_not_found(self):
        db = self._mock_db()
        db.execute_one.return_value = None
        mgr = UserManager(db)
        ctx = mgr.load_user_context(999)
        assert ctx is None


# ---------------------------------------------------------------------------
# Personal Access Token (PAT) tests
# ---------------------------------------------------------------------------

class TestPAT:
    def _mock_db(self):
        db = MagicMock()
        db.commit = MagicMock()
        return db

    def test_create_token_returns_raw(self):
        """create_api_token returns a raw token starting with cairn_."""
        db = self._mock_db()
        db.execute_one.return_value = {
            "id": 1, "name": "test", "token_prefix": "cairn_ab1234",
            "expires_at": None, "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        }
        mgr = UserManager(db)
        result = mgr.create_api_token(user_id=1, name="test")
        assert result["raw_token"].startswith("cairn_")
        assert len(result["raw_token"]) == 54  # "cairn_" + 48 hex chars
        assert result["name"] == "test"

    def test_resolve_valid_token(self):
        """resolve_api_token finds a valid token and returns UserContext."""
        db = self._mock_db()
        raw_token = "cairn_abc123def456abc123def456abc123def456abc123def456"
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        call_count = [0]
        def _execute_one(query, params=None):
            call_count[0] += 1
            if "FROM api_tokens" in query:
                assert params == (token_hash,)
                return {"user_id": 42, "expires_at": None}
            if "FROM users WHERE id" in query:
                return {
                    "id": 42, "username": "alice", "email": None,
                    "role": "user", "is_active": True,
                    "created_at": "2026-01-01", "updated_at": "2026-01-01",
                }
            return None

        db.execute_one.side_effect = _execute_one
        db.execute.return_value = [{"project_id": 1}]

        mgr = UserManager(db)
        ctx = mgr.resolve_api_token(raw_token)
        assert ctx is not None
        assert ctx.user_id == 42
        assert ctx.username == "alice"

    def test_resolve_invalid_token(self):
        """resolve_api_token returns None for unknown token."""
        db = self._mock_db()
        db.execute_one.return_value = None
        mgr = UserManager(db)
        ctx = mgr.resolve_api_token("cairn_nonexistent_token_value_here")
        assert ctx is None

    def test_resolve_expired_token(self):
        """resolve_api_token returns None for expired token."""
        db = self._mock_db()
        db.execute_one.return_value = {
            "user_id": 1,
            "expires_at": datetime(2020, 1, 1, tzinfo=timezone.utc),
        }
        mgr = UserManager(db)
        ctx = mgr.resolve_api_token("cairn_some_token_value_here_000000000000000000000000")
        assert ctx is None

    def test_list_tokens(self):
        """list_api_tokens returns metadata without secrets."""
        db = self._mock_db()
        db.execute.return_value = [
            {
                "id": 1, "name": "token1", "token_prefix": "cairn_ab12",
                "expires_at": None, "last_used_at": None,
                "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
                "is_active": True,
            },
        ]
        mgr = UserManager(db)
        tokens = mgr.list_api_tokens(user_id=1)
        assert len(tokens) == 1
        assert tokens[0]["name"] == "token1"
        assert "token_hash" not in tokens[0]


# ---------------------------------------------------------------------------
# OIDC user tests
# ---------------------------------------------------------------------------

class TestOIDCUser:
    def _mock_db(self):
        db = MagicMock()
        db.commit = MagicMock()
        return db

    def test_get_by_external_id_found(self):
        db = self._mock_db()
        db.execute_one.return_value = {
            "id": 5, "username": "oidc_user", "role": "user",
            "auth_provider": "oidc", "external_id": "sub123",
        }
        mgr = UserManager(db)
        result = mgr.get_by_external_id("oidc", "sub123")
        assert result is not None
        assert result["username"] == "oidc_user"

    def test_get_by_external_id_not_found(self):
        db = self._mock_db()
        db.execute_one.return_value = None
        mgr = UserManager(db)
        assert mgr.get_by_external_id("oidc", "missing") is None

    def test_create_oidc_user_no_password(self):
        """OIDC users are created without a password hash."""
        db = self._mock_db()
        db.execute_one.return_value = {
            "id": 10, "username": "jane", "email": "jane@example.com",
            "role": "user", "is_active": True,
            "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        }
        mgr = UserManager(db)
        result = mgr.create_oidc_user("sub456", "jane", email="jane@example.com")
        assert result["username"] == "jane"
        # Verify NULL was passed for password_hash
        insert_call = db.execute_one.call_args
        assert "NULL" in insert_call[0][0]

    def test_get_or_create_existing(self):
        """get_or_create_oidc_user returns existing user."""
        db = self._mock_db()
        call_count = [0]

        def _execute_one(query, params=None):
            call_count[0] += 1
            if "auth_provider" in query and "external_id" in query:
                return {
                    "id": 5, "username": "existing", "email": "e@x.com",
                    "role": "user", "auth_provider": "oidc", "external_id": "sub1",
                    "is_active": True,
                }
            if "FROM users WHERE id" in query:
                return {
                    "id": 5, "username": "existing", "email": "e@x.com",
                    "role": "user", "is_active": True,
                    "created_at": "2026-01-01", "updated_at": "2026-01-01",
                }
            return None

        db.execute_one.side_effect = _execute_one
        mgr = UserManager(db)
        result = mgr.get_or_create_oidc_user("sub1", {"email": "e@x.com"})
        assert result["username"] == "existing"

    def test_get_or_create_admin_from_groups(self):
        """Admin role is assigned when user is in a configured admin group."""
        db = self._mock_db()

        def _execute_one(query, params=None):
            if "auth_provider" in query and "external_id" in query and "SELECT" in query:
                return None  # Not found → create path
            if "FROM users WHERE username" in query:
                return None  # No collision
            if "INSERT INTO users" in query:
                # Verify admin role was passed
                assert params[2] == "admin", f"Expected admin role, got {params[2]}"
                return {
                    "id": 20, "username": params[0], "email": params[1],
                    "role": params[2], "is_active": True,
                    "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
                }
            return None

        db.execute_one.side_effect = _execute_one
        mgr = UserManager(db)
        result = mgr.get_or_create_oidc_user(
            "sub_new",
            {"preferred_username": "admin_user", "email": "a@b.c", "groups": ["cairn-admins"]},
            admin_groups=["cairn-admins"],
        )
        assert result["role"] == "admin"


# ---------------------------------------------------------------------------
# Unified token resolution tests
# ---------------------------------------------------------------------------

class TestResolveBearerToken:
    def test_jwt_path(self):
        """Valid JWT resolves to UserContext."""
        db = self._mock_db()
        token = create_access_token(1, "alice", "admin", secret=SECRET)
        db.execute_one.side_effect = lambda q, p=None: (
            {"id": 1, "username": "alice", "email": None, "role": "admin",
             "is_active": True, "created_at": "2026-01-01", "updated_at": "2026-01-01"}
            if "FROM users WHERE id" in q else None
        )
        db.execute.return_value = [{"project_id": 1}]
        mgr = UserManager(db)
        ctx = resolve_bearer_token(token, jwt_secret=SECRET, user_manager=mgr)
        assert ctx is not None
        assert ctx.username == "alice"

    def test_pat_path(self):
        """PAT resolves to UserContext when JWT fails."""
        db = self._mock_db()
        raw_token = "cairn_abc123def456abc123def456abc123def456abc123def456"
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        def _execute_one(query, params=None):
            if "FROM api_tokens" in query:
                return {"user_id": 5, "expires_at": None}
            if "FROM users WHERE id" in query:
                return {
                    "id": 5, "username": "bot", "email": None,
                    "role": "agent", "is_active": True,
                    "created_at": "2026-01-01", "updated_at": "2026-01-01",
                }
            return None

        db.execute_one.side_effect = _execute_one
        db.execute.return_value = [{"project_id": 10}]
        mgr = UserManager(db)
        ctx = resolve_bearer_token(raw_token, jwt_secret=SECRET, user_manager=mgr)
        assert ctx is not None
        assert ctx.username == "bot"
        assert ctx.role == "agent"

    def test_invalid_token(self):
        """Invalid token returns None."""
        db = self._mock_db()
        db.execute_one.return_value = None
        mgr = UserManager(db)
        ctx = resolve_bearer_token("garbage", jwt_secret=SECRET, user_manager=mgr)
        assert ctx is None

    def _mock_db(self):
        db = MagicMock()
        db.commit = MagicMock()
        return db


# ---------------------------------------------------------------------------
# OIDC state store tests
# ---------------------------------------------------------------------------

class TestOIDCStateStore:
    def test_create_and_consume(self):
        from cairn.core.oidc import OIDCStateStore
        store = OIDCStateStore(ttl_seconds=60)
        state, verifier = store.create("http://localhost:3000")
        assert len(state) > 20
        assert len(verifier) > 40
        # Consume should return (verifier, ui_origin)
        result = store.consume(state)
        assert result == (verifier, "http://localhost:3000")
        # Second consume returns None (already consumed)
        assert store.consume(state) is None

    def test_expired_state(self):
        from cairn.core.oidc import OIDCStateStore
        store = OIDCStateStore(ttl_seconds=0)  # Immediate expiry
        state, _ = store.create()
        import time
        time.sleep(0.01)
        assert store.consume(state) is None

    def test_invalid_state(self):
        from cairn.core.oidc import OIDCStateStore
        store = OIDCStateStore()
        assert store.consume("nonexistent") is None
