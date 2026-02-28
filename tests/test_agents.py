"""Tests for agent type definitions and registry (ca-150, ca-155)."""

from __future__ import annotations

import pytest

from cairn.core.agents import (
    AgentDefinition,
    AgentRegistry,
    BUILTIN_AGENTS,
    CAPABILITIES,
    validate_dispatch,
)


class TestAgentDefinition:
    """Test AgentDefinition dataclass behavior."""

    def test_basic_creation(self):
        defn = AgentDefinition(name="test", role="worker", description="A test agent")
        assert defn.name == "test"
        assert defn.role == "worker"
        assert defn.default_risk_tier == 1
        assert defn.allowed_tools == frozenset()
        assert defn.blocked_tools == frozenset()

    def test_is_coordinator(self):
        worker = AgentDefinition(name="w", role="worker", description="")
        coord = AgentDefinition(name="c", role="coordinator", description="")
        assert worker.is_coordinator is False
        assert coord.is_coordinator is True

    def test_is_restricted_no_tools(self):
        defn = AgentDefinition(name="w", role="worker", description="")
        assert defn.is_restricted is False

    def test_is_restricted_with_allowlist(self):
        defn = AgentDefinition(
            name="w", role="worker", description="",
            allowed_tools=frozenset({"search", "recall"}),
        )
        assert defn.is_restricted is True

    def test_is_restricted_with_blocklist(self):
        defn = AgentDefinition(
            name="w", role="worker", description="",
            blocked_tools=frozenset({"Bash"}),
        )
        assert defn.is_restricted is True

    def test_can_use_tool_unrestricted(self):
        defn = AgentDefinition(name="w", role="worker", description="")
        assert defn.can_use_tool("Bash") is True
        assert defn.can_use_tool("Edit") is True
        assert defn.can_use_tool("anything") is True

    def test_can_use_tool_allowlist(self):
        defn = AgentDefinition(
            name="r", role="researcher", description="",
            allowed_tools=frozenset({"search", "recall", "orient"}),
        )
        assert defn.can_use_tool("search") is True
        assert defn.can_use_tool("recall") is True
        assert defn.can_use_tool("Bash") is False
        assert defn.can_use_tool("Edit") is False

    def test_can_use_tool_blocklist(self):
        defn = AgentDefinition(
            name="c", role="coordinator", description="",
            blocked_tools=frozenset({"Edit", "Write", "Bash"}),
        )
        assert defn.can_use_tool("search") is True
        assert defn.can_use_tool("Edit") is False
        assert defn.can_use_tool("Bash") is False

    def test_blocklist_overrides_allowlist(self):
        defn = AgentDefinition(
            name="x", role="worker", description="",
            allowed_tools=frozenset({"search", "Bash"}),
            blocked_tools=frozenset({"Bash"}),
        )
        assert defn.can_use_tool("search") is True
        assert defn.can_use_tool("Bash") is False  # blocked takes priority

    def test_to_dict(self):
        defn = AgentDefinition(
            name="test-agent", role="worker", description="Test",
            default_risk_tier=2,
            allowed_tools=frozenset({"search"}),
            blocked_tools=frozenset({"Bash"}),
            system_prompt="Do stuff",
        )
        d = defn.to_dict()
        assert d["name"] == "test-agent"
        assert d["role"] == "worker"
        assert d["description"] == "Test"
        assert d["default_risk_tier"] == 2
        assert d["allowed_tools"] == ["search"]
        assert d["blocked_tools"] == ["Bash"]
        assert d["is_coordinator"] is False
        assert d["system_prompt"] == "Do stuff"

    def test_to_dict_truncates_long_system_prompt(self):
        defn = AgentDefinition(
            name="t", role="worker", description="",
            system_prompt="x" * 300,
        )
        d = defn.to_dict()
        assert len(d["system_prompt"]) == 203  # 200 + "..."
        assert d["system_prompt"].endswith("...")

    def test_frozen(self):
        defn = AgentDefinition(name="t", role="worker", description="")
        with pytest.raises(AttributeError):
            defn.name = "changed"

    # --- ca-155: capabilities, file_patterns, max_risk_tier ---

    def test_capabilities_default_empty(self):
        defn = AgentDefinition(name="t", role="worker", description="")
        assert defn.capabilities == frozenset()

    def test_has_capability_unrestricted(self):
        """No capabilities declared = assumed capable of everything."""
        defn = AgentDefinition(name="t", role="worker", description="")
        assert defn.has_capability("read_files") is True
        assert defn.has_capability("anything") is True

    def test_has_capability_restricted(self):
        defn = AgentDefinition(
            name="r", role="researcher", description="",
            capabilities=frozenset({"read_files", "search_context"}),
        )
        assert defn.has_capability("read_files") is True
        assert defn.has_capability("search_context") is True
        assert defn.has_capability("write_files") is False
        assert defn.has_capability("execute_code") is False

    def test_can_modify_file_unrestricted(self):
        defn = AgentDefinition(name="w", role="worker", description="")
        assert defn.can_modify_file("src/anything.py") is True
        assert defn.can_modify_file("tests/test_foo.py") is True

    def test_can_modify_file_with_patterns(self):
        defn = AgentDefinition(
            name="fe", role="worker", description="",
            file_patterns=frozenset({"src/ui/**/*.tsx", "src/ui/**/*.css"}),
        )
        assert defn.can_modify_file("src/ui/components/Button.tsx") is True
        assert defn.can_modify_file("src/ui/styles/main.css") is True
        assert defn.can_modify_file("src/backend/api.py") is False
        assert defn.can_modify_file("tests/test_ui.py") is False

    def test_is_restricted_with_file_patterns(self):
        defn = AgentDefinition(
            name="w", role="worker", description="",
            file_patterns=frozenset({"*.py"}),
        )
        assert defn.is_restricted is True

    def test_max_risk_tier_default_none(self):
        defn = AgentDefinition(name="t", role="worker", description="")
        assert defn.max_risk_tier is None

    def test_to_dict_includes_new_fields(self):
        defn = AgentDefinition(
            name="t", role="worker", description="Test",
            max_risk_tier=2,
            capabilities=frozenset({"read_files", "write_files"}),
            file_patterns=frozenset({"src/**/*.py"}),
        )
        d = defn.to_dict()
        assert d["max_risk_tier"] == 2
        assert d["capabilities"] == ["read_files", "write_files"]
        assert d["file_patterns"] == ["src/**/*.py"]


class TestAgentRegistry:
    """Test AgentRegistry management."""

    def test_builtin_agents_loaded(self):
        registry = AgentRegistry()
        assert registry.get("cairn-worker") is not None
        assert registry.get("cairn-coordinator") is not None
        assert registry.get("cairn-research") is not None
        assert registry.get("cairn-plan") is not None
        assert registry.get("cairn-build") is not None
        assert registry.get("cairn-reviewer") is not None

    def test_get_nonexistent(self):
        registry = AgentRegistry()
        assert registry.get("nonexistent") is None

    def test_get_or_default_existing(self):
        registry = AgentRegistry()
        defn = registry.get_or_default("cairn-coordinator")
        assert defn.name == "cairn-coordinator"
        assert defn.role == "coordinator"

    def test_get_or_default_none(self):
        registry = AgentRegistry()
        defn = registry.get_or_default(None)
        assert defn.name == "cairn-worker"

    def test_get_or_default_missing(self):
        registry = AgentRegistry()
        defn = registry.get_or_default("nonexistent")
        assert defn.name == "cairn-worker"

    def test_register_custom(self):
        registry = AgentRegistry()
        custom = AgentDefinition(
            name="my-agent", role="worker", description="Custom",
        )
        registry.register(custom)
        assert registry.get("my-agent") is custom

    def test_register_overrides_builtin(self):
        registry = AgentRegistry()
        override = AgentDefinition(
            name="cairn-worker", role="worker", description="Overridden",
        )
        registry.register(override)
        assert registry.get("cairn-worker").description == "Overridden"

    def test_list_sorted(self):
        registry = AgentRegistry()
        agents = registry.list()
        names = [a.name for a in agents]
        assert names == sorted(names)

    def test_list_by_role_worker(self):
        registry = AgentRegistry()
        workers = registry.list_by_role("worker")
        assert all(a.role == "worker" for a in workers)
        names = [a.name for a in workers]
        assert "cairn-worker" in names
        assert "cairn-build" in names

    def test_list_by_role_coordinator(self):
        registry = AgentRegistry()
        coords = registry.list_by_role("coordinator")
        assert len(coords) == 1
        assert coords[0].name == "cairn-coordinator"

    def test_list_by_role_empty(self):
        registry = AgentRegistry()
        assert registry.list_by_role("nonexistent") == []

    def test_to_dict(self):
        registry = AgentRegistry()
        result = registry.to_dict()
        assert isinstance(result, list)
        assert len(result) == len(BUILTIN_AGENTS)
        assert all(isinstance(d, dict) for d in result)


class TestValidateDispatch:
    """Test dispatch validation rules."""

    def test_worker_can_dispatch_to_subtask(self):
        worker = AgentDefinition(name="w", role="worker", description="")
        wi = {"item_type": "subtask", "parent_id": 1}
        errors = validate_dispatch(worker, wi)
        assert errors == []

    def test_worker_can_dispatch_to_task(self):
        worker = AgentDefinition(name="w", role="worker", description="")
        wi = {"item_type": "task", "parent_id": None}
        errors = validate_dispatch(worker, wi)
        assert errors == []

    def test_coordinator_cannot_dispatch_to_subtask(self):
        coord = AgentDefinition(name="c", role="coordinator", description="")
        wi = {"item_type": "subtask", "parent_id": 1}
        errors = validate_dispatch(coord, wi)
        assert len(errors) == 1
        assert "should not be dispatched to subtasks" in errors[0]

    def test_coordinator_can_dispatch_to_epic(self):
        coord = AgentDefinition(name="c", role="coordinator", description="")
        wi = {"item_type": "epic", "parent_id": None}
        errors = validate_dispatch(coord, wi)
        assert errors == []

    def test_coordinator_can_dispatch_to_task(self):
        coord = AgentDefinition(name="c", role="coordinator", description="")
        wi = {"item_type": "task", "parent_id": None}
        errors = validate_dispatch(coord, wi)
        assert errors == []

    def test_missing_item_type_defaults_to_task(self):
        coord = AgentDefinition(name="c", role="coordinator", description="")
        wi = {"parent_id": None}  # no item_type
        errors = validate_dispatch(coord, wi)
        assert errors == []

    # --- ca-155: max_risk_tier enforcement ---

    def test_risk_tier_ceiling_blocks_high_risk(self):
        """Agent with max_risk_tier=3 cannot take tier 1 work (lower = higher risk)."""
        researcher = AgentDefinition(
            name="r", role="researcher", description="",
            max_risk_tier=3,
        )
        wi = {"item_type": "task", "risk_tier": 1}
        errors = validate_dispatch(researcher, wi)
        assert len(errors) == 1
        assert "max risk tier" in errors[0]

    def test_risk_tier_ceiling_allows_matching_tier(self):
        researcher = AgentDefinition(
            name="r", role="researcher", description="",
            max_risk_tier=3,
        )
        wi = {"item_type": "task", "risk_tier": 3}
        errors = validate_dispatch(researcher, wi)
        assert errors == []

    def test_risk_tier_ceiling_allows_lower_risk(self):
        """Agent with max_risk_tier=2 can take tier 3 work (higher number = lower risk)."""
        planner = AgentDefinition(
            name="p", role="planner", description="",
            max_risk_tier=2,
        )
        wi = {"item_type": "task", "risk_tier": 3}
        errors = validate_dispatch(planner, wi)
        assert errors == []

    def test_risk_tier_none_means_no_limit(self):
        worker = AgentDefinition(name="w", role="worker", description="")
        wi = {"item_type": "task", "risk_tier": 0}
        errors = validate_dispatch(worker, wi)
        assert errors == []

    def test_risk_tier_missing_from_work_item(self):
        """No risk_tier on work item = no risk validation."""
        researcher = AgentDefinition(
            name="r", role="researcher", description="",
            max_risk_tier=3,
        )
        wi = {"item_type": "task"}
        errors = validate_dispatch(researcher, wi)
        assert errors == []

    def test_coordinator_subtask_plus_risk_tier_two_errors(self):
        """Both coordinator boundary and risk tier violations can fire together."""
        coord = AgentDefinition(
            name="c", role="coordinator", description="",
            max_risk_tier=3,
        )
        wi = {"item_type": "subtask", "parent_id": 1, "risk_tier": 0}
        errors = validate_dispatch(coord, wi)
        assert len(errors) == 2


class TestBuiltinAgents:
    """Verify built-in agent definitions have correct properties."""

    def test_coordinator_has_tool_restrictions(self):
        coord = BUILTIN_AGENTS["cairn-coordinator"]
        assert coord.is_coordinator is True
        assert coord.is_restricted is True
        assert coord.can_use_tool("work_items") is True
        assert coord.can_use_tool("dispatch") is True
        assert coord.can_use_tool("Edit") is False
        assert coord.can_use_tool("Write") is False
        assert coord.can_use_tool("Bash") is False
        assert coord.can_use_tool("NotebookEdit") is False

    def test_worker_unrestricted(self):
        worker = BUILTIN_AGENTS["cairn-worker"]
        assert worker.is_coordinator is False
        assert worker.is_restricted is False
        assert worker.can_use_tool("Edit") is True
        assert worker.can_use_tool("Bash") is True

    def test_researcher_high_risk_tier(self):
        researcher = BUILTIN_AGENTS["cairn-research"]
        assert researcher.default_risk_tier == 3

    def test_planner_moderate_risk_tier(self):
        planner = BUILTIN_AGENTS["cairn-plan"]
        assert planner.default_risk_tier == 2

    def test_all_have_system_prompts(self):
        for name, defn in BUILTIN_AGENTS.items():
            assert defn.system_prompt, f"{name} missing system_prompt"

    def test_all_have_descriptions(self):
        for name, defn in BUILTIN_AGENTS.items():
            assert defn.description, f"{name} missing description"

    # --- ca-155: capabilities, reviewer, max_risk_tier ---

    def test_all_have_capabilities(self):
        for name, defn in BUILTIN_AGENTS.items():
            assert defn.capabilities, f"{name} missing capabilities"

    def test_all_capabilities_are_recognized(self):
        """All declared capabilities must be in the CAPABILITIES constant."""
        for name, defn in BUILTIN_AGENTS.items():
            for cap in defn.capabilities:
                assert cap in CAPABILITIES, f"{name} declares unknown capability '{cap}'"

    def test_coordinator_capabilities(self):
        coord = BUILTIN_AGENTS["cairn-coordinator"]
        assert coord.has_capability("dispatch_agents")
        assert coord.has_capability("create_work_items")
        assert not coord.has_capability("write_files")
        assert not coord.has_capability("execute_code")

    def test_researcher_capabilities(self):
        researcher = BUILTIN_AGENTS["cairn-research"]
        assert researcher.has_capability("read_files")
        assert researcher.has_capability("search_context")
        assert not researcher.has_capability("write_files")
        assert not researcher.has_capability("dispatch_agents")

    def test_researcher_max_risk_tier(self):
        researcher = BUILTIN_AGENTS["cairn-research"]
        assert researcher.max_risk_tier == 3

    def test_planner_max_risk_tier(self):
        planner = BUILTIN_AGENTS["cairn-plan"]
        assert planner.max_risk_tier == 2

    def test_worker_no_risk_ceiling(self):
        worker = BUILTIN_AGENTS["cairn-worker"]
        assert worker.max_risk_tier is None

    def test_coordinator_no_risk_ceiling(self):
        coord = BUILTIN_AGENTS["cairn-coordinator"]
        assert coord.max_risk_tier is None

    def test_reviewer_exists(self):
        reviewer = BUILTIN_AGENTS["cairn-reviewer"]
        assert reviewer.role == "reviewer"
        assert reviewer.max_risk_tier == 2
        assert reviewer.has_capability("review_deliverables")
        assert reviewer.has_capability("read_files")
        assert not reviewer.has_capability("write_files")

    def test_six_builtin_agents(self):
        assert len(BUILTIN_AGENTS) == 6
