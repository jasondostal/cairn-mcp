"""Tests for ModelRouter and OperationLLM."""

import pytest
from datetime import date
from unittest.mock import patch

from cairn.config import LLMConfig, RouterConfig, ModelTierConfig
from cairn.llm.interface import LLMInterface, LLMResponse
from cairn.llm.router import ModelRouter, OperationLLM, VALID_TIERS


class FakeLLM(LLMInterface):
    """Fake LLM that records calls and returns a configurable response."""

    def __init__(self, name: str = "fake", response: str = "ok"):
        self.name = name
        self._response = response
        self.calls: list[dict] = []

    def generate(self, messages: list[dict], max_tokens: int = 1024) -> str:
        self.calls.append({"messages": messages, "max_tokens": max_tokens})
        return self._response

    def get_model_name(self) -> str:
        return self.name

    def get_context_size(self) -> int:
        return 128000

    def supports_tool_use(self) -> bool:
        return True

    def generate_with_tools(self, messages, tools, max_tokens=2048):
        return LLMResponse(text="tool response", stop_reason="end_turn")


def _make_router(
    capable_backend="ollama",
    fast_backend="ollama",
    chat_backend="ollama",
    capable_budget=0,
    fast_budget=0,
    chat_budget=0,
    capable_model="",
    fast_model="",
    chat_model="",
):
    """Build a ModelRouter with FakeLLM backends injected."""
    router_config = RouterConfig(
        enabled=True,
        capable=ModelTierConfig(backend=capable_backend, model=capable_model, daily_budget=capable_budget),
        fast=ModelTierConfig(backend=fast_backend, model=fast_model, daily_budget=fast_budget),
        chat=ModelTierConfig(backend=chat_backend, model=chat_model, daily_budget=chat_budget),
    )
    llm_config = LLMConfig(backend="ollama")

    # Patch get_llm to return FakeLLMs
    fake_backends = {}

    def fake_get_llm(config):
        key = f"{config.backend}:{getattr(config, f'{config.backend}_model', '')}"
        if key not in fake_backends:
            fake_backends[key] = FakeLLM(name=key)
        return fake_backends[key]

    with patch("cairn.llm.router.get_llm", side_effect=fake_get_llm):
        router = ModelRouter(router_config, llm_config)

    return router, fake_backends


class TestModelRouter:
    """ModelRouter tier resolution and delegation."""

    def test_resolves_tier_to_correct_backend(self):
        router, backends = _make_router(
            capable_backend="bedrock",
            fast_backend="ollama",
            chat_backend="ollama",
        )
        # capable should resolve to bedrock
        capable_llm = router._resolve_backend("capable")
        assert "bedrock" in capable_llm.get_model_name()

        # fast should resolve to ollama
        fast_llm = router._resolve_backend("fast")
        assert "ollama" in fast_llm.get_model_name()

    def test_generate_delegates_to_correct_backend(self):
        router, backends = _make_router()
        result = router.generate([{"role": "user", "content": "hello"}], tier="capable")
        assert result == "ok"

    def test_for_operation_returns_operation_llm(self):
        router, _ = _make_router()
        op_llm = router.for_operation("capable")
        assert isinstance(op_llm, OperationLLM)

    def test_for_operation_invalid_tier_raises(self):
        router, _ = _make_router()
        with pytest.raises(ValueError, match="Unknown tier"):
            router.for_operation("invalid")

    def test_all_tiers_same_backend_deduplicates(self):
        """When all tiers use the same backend+model, only one instance is created."""
        router, backends = _make_router()
        # All default to ollama — should have only 1 backend
        assert len(router._backends) == 1


class TestOperationLLM:
    """OperationLLM delegation to router."""

    def test_generate_delegates_with_tier(self):
        router, _ = _make_router()
        op = router.for_operation("fast")
        result = op.generate([{"role": "user", "content": "test"}])
        assert result == "ok"

    def test_get_model_name(self):
        router, _ = _make_router()
        op = router.for_operation("capable")
        name = op.get_model_name()
        assert isinstance(name, str) and len(name) > 0

    def test_get_context_size(self):
        router, _ = _make_router()
        op = router.for_operation("fast")
        size = op.get_context_size()
        assert size > 0

    def test_supports_tool_use(self):
        router, _ = _make_router()
        op = router.for_operation("chat")
        assert op.supports_tool_use() is True


class TestBudgetEnforcement:
    """Daily budget limits and fallback behavior."""

    def test_over_budget_falls_back_to_fast(self):
        router, backends = _make_router(
            capable_backend="bedrock",
            fast_backend="ollama",
            capable_budget=100,
        )
        # Manually push capable over budget
        capable_key = router._tier_keys["capable"]
        router._daily_counters[capable_key] = 200

        # Should fall back to fast
        backend = router._resolve_backend("capable")
        assert "ollama" in backend.get_model_name()

    def test_under_budget_uses_original(self):
        router, backends = _make_router(
            capable_backend="bedrock",
            fast_backend="ollama",
            capable_budget=1000,
        )
        # Under budget — should use capable
        backend = router._resolve_backend("capable")
        assert "bedrock" in backend.get_model_name()

    def test_no_budget_always_passes(self):
        router, _ = _make_router()
        # No budgets set — should always work
        for _ in range(100):
            router.generate([{"role": "user", "content": "x" * 1000}], tier="capable")

    def test_daily_counter_resets_on_date_change(self):
        router, _ = _make_router(capable_budget=100)
        capable_key = router._tier_keys["capable"]
        router._daily_counters[capable_key] = 200

        # Simulate date change
        router._counter_date = date(2020, 1, 1)
        router._reset_if_new_day()

        # Counters should be cleared
        assert router._daily_counters.get(capable_key, 0) == 0

    def test_generate_increments_counter(self):
        router, _ = _make_router()
        capable_key = router._tier_keys["capable"]
        initial = router._daily_counters.get(capable_key, 0)
        router.generate([{"role": "user", "content": "hello world"}], tier="capable")
        assert router._daily_counters.get(capable_key, 0) > initial


class TestDisabledRouter:
    """When router is disabled, services.py should use single LLM."""

    def test_router_config_defaults_to_disabled(self):
        config = RouterConfig()
        assert config.enabled is False

    def test_model_tier_config_defaults(self):
        tier = ModelTierConfig()
        assert tier.backend == ""
        assert tier.model == ""
        assert tier.daily_budget == 0

    def test_valid_tiers_constant(self):
        assert VALID_TIERS == ("capable", "fast", "chat")
