"""Model router — routes operations to different LLM backends by tier.

Three tiers:
  - capable: extraction, knowledge extraction (quality-critical)
  - fast: enrichment, digest, clustering, synthesis, consolidation, classification
  - chat: user-facing conversations

Each tier can be mapped to a different backend+model combo with independent
daily token budgets. Over-budget tiers fall back to the "fast" tier.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import date

from cairn.config import LLMConfig, RouterConfig
from cairn.llm import get_llm
from collections.abc import Iterator

from cairn.llm.interface import LLMInterface, LLMResponse, StreamEvent

logger = logging.getLogger(__name__)

VALID_TIERS = ("capable", "fast", "chat")


class OperationLLM(LLMInterface):
    """Thin LLMInterface wrapper bound to a fixed tier.

    All existing components see a normal LLMInterface — zero code changes.
    Delegates generate() to the router with the tier tag attached.
    """

    def __init__(self, router: ModelRouter, tier: str):
        self._router = router
        self._tier = tier

    def generate(self, messages: list[dict], max_tokens: int = 1024) -> str:
        return self._router.generate(messages, max_tokens, tier=self._tier)

    def get_model_name(self) -> str:
        backend = self._router._resolve_backend(self._tier)
        return backend.get_model_name()

    def get_context_size(self) -> int:
        backend = self._router._resolve_backend(self._tier)
        return backend.get_context_size()

    def supports_tool_use(self) -> bool:
        backend = self._router._resolve_backend(self._tier)
        return backend.supports_tool_use()

    def generate_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int = 2048,
    ) -> LLMResponse:
        backend = self._router._resolve_backend(self._tier)
        return backend.generate_with_tools(messages, tools, max_tokens)

    def generate_stream(
        self, messages: list[dict], max_tokens: int = 1024,
    ) -> Iterator[StreamEvent]:
        backend = self._router._resolve_backend(self._tier)
        yield from backend.generate_stream(messages, max_tokens)

    def generate_with_tools_stream(
        self,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int = 2048,
    ) -> Iterator[StreamEvent]:
        backend = self._router._resolve_backend(self._tier)
        yield from backend.generate_with_tools_stream(messages, tools, max_tokens)


class ModelRouter(LLMInterface):
    """Routes LLM calls to tier-specific backends with daily budget enforcement.

    When a tier exceeds its daily budget, calls fall back to the "fast" tier.
    Budgets are tracked in-memory and reset on date change.
    """

    def __init__(self, router_config: RouterConfig, llm_config: LLMConfig):

        self._router_config = router_config
        self._llm_config = llm_config

        # Build a backend instance per unique (backend, model) combo
        self._backends: dict[str, LLMInterface] = {}
        self._tier_keys: dict[str, str] = {}  # tier -> backend_key
        self._budgets: dict[str, int] = {}    # backend_key -> daily limit

        for tier_name in VALID_TIERS:
            tier_cfg = getattr(router_config, tier_name)
            backend_name = tier_cfg.backend or llm_config.backend
            model_name = tier_cfg.model  # may be empty

            # Build a backend key for dedup
            key = f"{backend_name}:{model_name}" if model_name else backend_name
            self._tier_keys[tier_name] = key

            if tier_cfg.daily_budget > 0:
                self._budgets[key] = tier_cfg.daily_budget

            if key not in self._backends:
                # Build an LLMConfig for this specific backend+model
                if model_name:
                    model_field = f"{backend_name}_model"
                    if backend_name == "openai":
                        model_field = "openai_model"
                    overrides = {model_field: model_name} if hasattr(llm_config, model_field) else {}
                    tier_llm_config = replace(llm_config, backend=backend_name, **overrides)
                elif backend_name != llm_config.backend:
                    tier_llm_config = replace(llm_config, backend=backend_name)
                else:
                    tier_llm_config = llm_config

                self._backends[key] = get_llm(tier_llm_config)

        # Daily counters (in-memory, reset on date change)
        self._daily_counters: dict[str, int] = {}
        self._counter_date: date = date.today()

        logger.info(
            "ModelRouter ready: capable=%s, fast=%s, chat=%s, budgets=%s",
            self._tier_keys.get("capable"),
            self._tier_keys.get("fast"),
            self._tier_keys.get("chat"),
            {k: v for k, v in self._budgets.items()} or "none",
        )

    def _reset_if_new_day(self) -> None:
        """Reset daily counters if the date has changed."""
        today = date.today()
        if today != self._counter_date:
            self._daily_counters.clear()
            self._counter_date = today
            logger.info("ModelRouter: daily counters reset for %s", today)

    def _resolve_backend(self, tier: str) -> LLMInterface:
        """Resolve a tier to its backend, with budget fallback."""
        self._reset_if_new_day()

        key = self._tier_keys.get(tier, self._tier_keys.get("capable", ""))

        # Check budget
        if key in self._budgets:
            used = self._daily_counters.get(key, 0)
            if used >= self._budgets[key]:
                fallback_key = self._tier_keys.get("fast", key)
                if fallback_key != key:
                    logger.warning(
                        "ModelRouter: tier '%s' (%s) over daily budget (%d/%d tokens), falling back to fast (%s)",
                        tier, key, used, self._budgets[key], fallback_key,
                    )
                    key = fallback_key

        return self._backends[key]

    def _record_tokens(self, tier: str, tokens: int) -> None:
        """Increment the daily counter for a tier's backend."""
        key = self._tier_keys.get(tier, "")
        if key:
            self._daily_counters[key] = self._daily_counters.get(key, 0) + tokens

    def for_operation(self, tier: str) -> OperationLLM:
        """Return an LLMInterface bound to the given tier."""
        if tier not in VALID_TIERS:
            raise ValueError(f"Unknown tier: {tier!r}. Must be one of {VALID_TIERS}")
        return OperationLLM(self, tier)

    def generate(self, messages: list[dict], max_tokens: int = 1024, tier: str | None = None) -> str:
        """Generate via the appropriate backend for the tier."""
        effective_tier = tier or "capable"
        backend = self._resolve_backend(effective_tier)
        result = backend.generate(messages, max_tokens)
        # Estimate tokens for budget tracking (actual counts go through stats)
        token_est = sum(len(m.get("content", "")) for m in messages) // 4 + len(result) // 4
        self._record_tokens(effective_tier, token_est)
        return result

    def get_model_name(self) -> str:
        backend = self._resolve_backend("capable")
        return backend.get_model_name()

    def get_context_size(self) -> int:
        backend = self._resolve_backend("capable")
        return backend.get_context_size()

    def supports_tool_use(self) -> bool:
        backend = self._resolve_backend("chat")
        return backend.supports_tool_use()

    def generate_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int = 2048,
    ) -> LLMResponse:
        backend = self._resolve_backend("chat")
        return backend.generate_with_tools(messages, tools, max_tokens)

    def generate_with_tools_stream(
        self,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int = 2048,
    ) -> Iterator[StreamEvent]:
        backend = self._resolve_backend("chat")
        yield from backend.generate_with_tools_stream(messages, tools, max_tokens)
