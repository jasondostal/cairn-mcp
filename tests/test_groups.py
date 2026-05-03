"""Tests for group management — CRUD, membership, project access, OIDC sync (ca-171)."""

from unittest.mock import MagicMock, patch
import pytest

from cairn.core.user import (
    UserContext,
    UserManager,
    set_user,
    clear_user,
)


@pytest.fixture
def db():
    """Mock database with execute/execute_one/commit."""
    mock = MagicMock()
    mock.commit = MagicMock()
    return mock


@pytest.fixture
def mgr(db):
    return UserManager(db)


class TestGroupCRUD:

    def test_create_group(self, mgr, db):
        db.execute_one.return_value = {
            "id": 1, "name": "devs", "description": "Developers",
            "source": "manual",
            "created_at": MagicMock(isoformat=lambda: "2026-01-01T00:00:00"),
            "updated_at": MagicMock(isoformat=lambda: "2026-01-01T00:00:00"),
        }
        result = mgr.create_group("devs", "Developers")
        assert result["name"] == "devs"
        assert result["source"] == "manual"
        db.commit.assert_called()

    def test_get_group(self, mgr, db):
        db.execute_one.return_value = {
            "id": 1, "name": "devs", "description": "",
            "source": "manual",
            "created_at": MagicMock(isoformat=lambda: "2026-01-01T00:00:00"),
            "updated_at": MagicMock(isoformat=lambda: "2026-01-01T00:00:00"),
        }
        result = mgr.get_group(1)
        assert result["id"] == 1

    def test_get_group_not_found(self, mgr, db):
        db.execute_one.return_value = None
        assert mgr.get_group(999) is None

    def test_list_groups(self, mgr, db):
        db.execute.return_value = [
            {
                "id": 1, "name": "devs", "description": "",
                "source": "manual", "member_count": 3, "project_count": 2,
                "created_at": MagicMock(isoformat=lambda: "2026-01-01T00:00:00"),
                "updated_at": MagicMock(isoformat=lambda: "2026-01-01T00:00:00"),
                "_total": 1,
            }
        ]
        result = mgr.list_groups()
        assert result["total"] == 1
        assert len(result["items"]) == 1
        assert result["items"][0]["member_count"] == 3

    def test_delete_group(self, mgr, db):
        assert mgr.delete_group(1) is True
        db.execute.assert_called()
        db.commit.assert_called()


class TestGroupMembership:

    def test_add_member(self, mgr, db):
        mgr.add_group_member(1, 10)
        db.execute.assert_called()
        db.commit.assert_called()

    def test_remove_member(self, mgr, db):
        mgr.remove_group_member(1, 10)
        db.execute.assert_called()
        db.commit.assert_called()

    def test_list_group_members(self, mgr, db):
        db.execute.return_value = [
            {
                "id": 10, "username": "alice", "email": "a@b.com",
                "role": "user",
                "added_at": MagicMock(isoformat=lambda: "2026-01-01T00:00:00"),
            }
        ]
        members = mgr.list_group_members(1)
        assert len(members) == 1
        assert members[0]["username"] == "alice"


class TestGroupProjectAccess:

    def test_add_group_project(self, mgr, db):
        mgr.add_group_project(1, 5, "member")
        db.execute.assert_called()
        db.commit.assert_called()

    def test_list_group_projects(self, mgr, db):
        db.execute.return_value = [
            {
                "id": 5, "name": "cairn", "role": "member",
                "granted_at": MagicMock(isoformat=lambda: "2026-01-01T00:00:00"),
            }
        ]
        projects = mgr.list_group_projects(1)
        assert len(projects) == 1
        assert projects[0]["project_name"] == "cairn"


class TestAccessibleProjectIds:
    """get_accessible_project_ids includes group-sourced projects."""

    def test_union_direct_and_group(self, mgr, db):
        """Returns union of direct membership + group-based access."""
        db.execute.return_value = [
            {"project_id": 1},  # direct
            {"project_id": 2},  # group-based
            {"project_id": 3},  # group-based
        ]
        ids = mgr.get_accessible_project_ids(10)
        assert ids == {1, 2, 3}
        # Verify the UNION query was used
        call_args = db.execute.call_args
        assert "UNION" in call_args[0][0]

    def test_empty_when_no_memberships(self, mgr, db):
        db.execute.return_value = []
        ids = mgr.get_accessible_project_ids(999)
        assert ids == set()


class TestOIDCGroupSync:

    def test_sync_creates_missing_groups(self, mgr, db):
        """sync_oidc_groups creates groups that don't exist yet."""
        # get_group_by_name returns None (group doesn't exist)
        db.execute_one.return_value = None
        # After create_group, subsequent queries find groups
        db.execute.side_effect = [
            # claimed_rows (SELECT id FROM groups WHERE name IN ...)
            [{"id": 1}],
            # current_rows (OIDC groups user is in)
            [],
        ]

        # Mock create_group to track calls
        created = []
        original_create = mgr.create_group

        def mock_create(name, description="", source="manual"):
            created.append(name)
            return {"id": len(created), "name": name, "description": description,
                    "source": source, "created_at": "t", "updated_at": "t"}

        mgr.create_group = mock_create
        mgr.get_group_by_name = MagicMock(return_value=None)
        mgr.add_group_member = MagicMock()

        mgr.sync_oidc_groups(10, ["engineers"])

        assert "engineers" in created
        mgr.add_group_member.assert_called()

    def test_sync_removes_stale_groups(self, mgr, db):
        """sync_oidc_groups removes user from OIDC groups no longer in claims."""
        mgr.get_group_by_name = MagicMock(return_value={"id": 1, "name": "old"})

        db.execute.side_effect = [
            # claimed_rows
            [{"id": 2}],
            # current_rows (user is in group 1 which is OIDC but no longer claimed)
            [{"group_id": 1}],
        ]

        mgr.add_group_member = MagicMock()
        mgr.remove_group_member = MagicMock()

        mgr.sync_oidc_groups(10, ["new-group"])

        # Should add to group 2 and remove from group 1
        mgr.add_group_member.assert_called_with(2, 10)
        mgr.remove_group_member.assert_called_with(1, 10)


class TestUserGroups:

    def test_get_user_groups(self, mgr, db):
        db.execute.return_value = [
            {
                "id": 1, "name": "devs", "description": "Developers",
                "source": "manual",
                "added_at": MagicMock(isoformat=lambda: "2026-01-01T00:00:00"),
            }
        ]
        groups = mgr.get_user_groups(10)
        assert len(groups) == 1
        assert groups[0]["name"] == "devs"



