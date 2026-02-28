"""Tests for affinity routing — agent-to-work matching (ca-157)."""

from __future__ import annotations

import pytest

from cairn.core.affinity import (
    AffinityScore,
    rank_agents,
    score_agent,
    suggest_agent,
    _infer_capabilities,
)
from cairn.core.agents import AgentDefinition, AgentRegistry


def _worker(name="worker", **kw):
    return AgentDefinition(name=name, role="worker", description="Test worker", **kw)


def _coordinator(name="coord", **kw):
    return AgentDefinition(name=name, role="coordinator", description="Test coord", **kw)


class TestAffinityScore:
    """Test AffinityScore dataclass."""

    def test_to_dict_basic(self):
        s = AffinityScore(agent_name="a", score=0.75, reasons=("idle",))
        d = s.to_dict()
        assert d["agent_name"] == "a"
        assert d["score"] == 0.75
        assert d["reasons"] == ["idle"]
        assert "disqualified" not in d

    def test_to_dict_disqualified(self):
        s = AffinityScore(
            agent_name="a", score=0.0,
            disqualified=True, disqualify_reason="risk too high",
        )
        d = s.to_dict()
        assert d["disqualified"] is True
        assert d["disqualify_reason"] == "risk too high"


class TestScoreAgent:
    """Test individual agent scoring."""

    def test_basic_score_no_history(self):
        agent = _worker()
        wi = {"item_type": "task", "project": "proj"}
        s = score_agent(agent, wi)
        assert s.score > 0
        assert not s.disqualified

    def test_project_familiarity_boost(self):
        agent = _worker()
        wi = {"item_type": "task", "project": "proj"}
        history = [
            {"project": "proj", "title": "prev work", "description": "did stuff"},
            {"project": "proj", "title": "more work", "description": "more stuff"},
        ]
        s_with = score_agent(agent, wi, agent_history=history)
        s_without = score_agent(agent, wi)
        assert s_with.score > s_without.score

    def test_file_affinity_boost(self):
        agent = _worker()
        wi = {
            "item_type": "task", "project": "proj",
            "title": "Fix src/api.py",
            "description": "Update the API endpoint in src/api.py",
        }
        history_match = [
            {"project": "proj", "title": "Refactor src/api.py", "description": "Changed src/api.py"},
        ]
        history_miss = [
            {"project": "proj", "title": "Update docs", "description": "Changed README.md"},
        ]
        s_match = score_agent(agent, wi, agent_history=history_match)
        s_miss = score_agent(agent, wi, agent_history=history_miss)
        assert s_match.score > s_miss.score

    def test_disqualified_coordinator_on_subtask(self):
        agent = _coordinator()
        wi = {"item_type": "subtask", "project": "proj", "parent_id": 1}
        s = score_agent(agent, wi)
        assert s.disqualified is True
        assert s.score == 0.0

    def test_risk_tier_disqualifies(self):
        agent = _worker(max_risk_tier=3)
        wi = {"item_type": "task", "project": "proj", "risk_tier": 0}
        s = score_agent(agent, wi)
        assert s.disqualified is True

    def test_load_penalty(self):
        agent = _worker()
        wi = {"item_type": "task", "project": "proj"}
        s_idle = score_agent(agent, wi, active_items_count=0)
        s_busy = score_agent(agent, wi, active_items_count=2, max_concurrent=3)
        s_full = score_agent(agent, wi, active_items_count=3, max_concurrent=3)
        assert s_idle.score > s_busy.score
        assert s_busy.score > s_full.score

    def test_capability_match(self):
        good = _worker(capabilities=frozenset({"read_files", "write_files", "execute_code"}))
        partial = _worker(name="partial", capabilities=frozenset({"read_files"}))
        wi = {"item_type": "task", "project": "proj"}  # needs read/write/execute
        s_good = score_agent(good, wi)
        s_partial = score_agent(partial, wi)
        assert s_good.score > s_partial.score

    def test_no_file_paths_neutral(self):
        """Work items with no file paths don't penalize file affinity."""
        agent = _worker()
        wi = {"item_type": "task", "project": "proj", "title": "Do something", "description": "no files mentioned"}
        s = score_agent(agent, wi)
        assert not s.disqualified


class TestRankAgents:
    """Test agent ranking."""

    def test_rank_returns_all_agents(self):
        registry = AgentRegistry()
        wi = {"item_type": "task", "project": "proj"}
        ranked = rank_agents(registry, wi)
        assert len(ranked) == len(registry.list())

    def test_disqualified_last(self):
        registry = AgentRegistry()
        wi = {"item_type": "subtask", "project": "proj", "parent_id": 1}
        ranked = rank_agents(registry, wi)
        # Coordinator should be at the end (disqualified)
        disqualified = [s for s in ranked if s.disqualified]
        qualified = [s for s in ranked if not s.disqualified]
        assert len(disqualified) >= 1
        assert all(s.agent_name != "cairn-coordinator" for s in qualified)

    def test_history_affects_ranking(self):
        registry = AgentRegistry()
        wi = {"item_type": "task", "project": "proj", "title": "Fix src/api.py"}
        histories = {
            "cairn-worker": [
                {"project": "proj", "title": "Edit src/api.py", "description": "Changed src/api.py"},
            ],
        }
        ranked = rank_agents(registry, wi, agent_histories=histories)
        # cairn-worker should rank higher than cairn-build (same role but more context)
        worker_idx = next(i for i, s in enumerate(ranked) if s.agent_name == "cairn-worker")
        build_idx = next(i for i, s in enumerate(ranked) if s.agent_name == "cairn-build")
        assert worker_idx < build_idx

    def test_load_affects_ranking(self):
        registry = AgentRegistry()
        wi = {"item_type": "task", "project": "proj"}
        counts = {"cairn-worker": 3, "cairn-build": 0}
        ranked = rank_agents(registry, wi, active_counts=counts)
        worker_score = next(s for s in ranked if s.agent_name == "cairn-worker")
        build_score = next(s for s in ranked if s.agent_name == "cairn-build")
        assert build_score.score > worker_score.score


class TestSuggestAgent:
    """Test top agent suggestion."""

    def test_suggest_returns_best(self):
        registry = AgentRegistry()
        wi = {"item_type": "task", "project": "proj"}
        suggestion = suggest_agent(registry, wi)
        assert suggestion is not None
        assert not suggestion.disqualified
        assert suggestion.score > 0

    def test_suggest_none_when_all_disqualified(self):
        registry = AgentRegistry()
        # Register only a coordinator
        for name in list(registry._agents.keys()):
            if name != "cairn-coordinator":
                del registry._agents[name]
        wi = {"item_type": "subtask", "project": "proj", "parent_id": 1}
        suggestion = suggest_agent(registry, wi)
        assert suggestion is None

    def test_suggest_for_epic(self):
        registry = AgentRegistry()
        wi = {"item_type": "epic", "project": "proj"}
        suggestion = suggest_agent(registry, wi)
        assert suggestion is not None
        # Coordinator should score well for epics due to capability match
        ranked = rank_agents(registry, wi)
        coord = next(s for s in ranked if s.agent_name == "cairn-coordinator")
        assert not coord.disqualified


class TestInferCapabilities:
    """Test capability inference from work item type."""

    def test_task_needs_implementation(self):
        caps = _infer_capabilities({"item_type": "task"})
        assert "read_files" in caps
        assert "write_files" in caps
        assert "execute_code" in caps

    def test_epic_needs_orchestration(self):
        caps = _infer_capabilities({"item_type": "epic"})
        assert "dispatch_agents" in caps
        assert "create_work_items" in caps

    def test_subtask_like_task(self):
        caps = _infer_capabilities({"item_type": "subtask"})
        assert "write_files" in caps
