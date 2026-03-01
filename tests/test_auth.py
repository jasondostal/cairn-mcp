"""Tests for cairn.core.user — UserContext, JWT, password, and contextvar operations."""

import threading
from unittest.mock import MagicMock

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
