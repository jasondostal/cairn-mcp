"""Tests for cairn.core.stats — ModelStats thread-safe counters."""

from cairn.core.stats import ModelStats, init_embedding_stats, init_llm_stats
import cairn.core.stats as stats_module


class TestModelStats:
    def test_initial_state(self):
        s = ModelStats("bedrock", "titan-v2")
        assert s.backend == "bedrock"
        assert s.model == "titan-v2"
        assert s.health == "unknown"

    def test_record_call(self):
        s = ModelStats("bedrock", "titan-v2")
        s.record_call(tokens_est=100)
        assert s.health == "healthy"
        d = s.to_dict()
        assert d["stats"]["calls"] == 1
        assert d["stats"]["tokens_est"] == 100
        assert d["stats"]["errors"] == 0
        assert d["stats"]["last_call"] is not None

    def test_record_error(self):
        s = ModelStats("bedrock", "titan-v2")
        s.record_call()
        s.record_error("ThrottlingException")
        assert s.health == "degraded"
        d = s.to_dict()
        assert d["stats"]["errors"] == 1
        assert d["stats"]["last_error_msg"] == "ThrottlingException"

    def test_unhealthy_after_3_consecutive_errors(self):
        s = ModelStats("bedrock", "titan-v2")
        s.record_error("e1")
        s.record_error("e2")
        s.record_error("e3")
        assert s.health == "unhealthy"

    def test_degraded_not_unhealthy_with_mixed(self):
        s = ModelStats("bedrock", "titan-v2")
        s.record_call()
        s.record_error("e1")
        s.record_call()
        assert s.health == "degraded"

    def test_healthy_after_window_clears(self):
        s = ModelStats("bedrock", "titan-v2")
        s.record_error("old")
        # Push 5 successes to fill the window (maxlen=5)
        for _ in range(5):
            s.record_call()
        assert s.health == "healthy"

    def test_tokens_accumulate(self):
        s = ModelStats("bedrock", "titan-v2")
        s.record_call(tokens_est=50)
        s.record_call(tokens_est=75)
        s.record_call(tokens_est=25)
        assert s.to_dict()["stats"]["tokens_est"] == 150
        assert s.to_dict()["stats"]["calls"] == 3

    def test_to_dict_no_deadlock(self):
        """to_dict calls health property — both acquire lock. RLock prevents deadlock."""
        s = ModelStats("local", "minilm")
        s.record_call(tokens_est=10)
        d = s.to_dict()
        assert d["health"] == "healthy"
        assert d["backend"] == "local"
        assert d["model"] == "minilm"


class TestStatsSingletons:
    def test_init_embedding_stats(self):
        result = init_embedding_stats("bedrock", "titan-v2")
        assert result is stats_module.embedding_stats
        assert result.backend == "bedrock"

    def test_init_llm_stats(self):
        result = init_llm_stats("ollama", "llama3.2")
        assert result is stats_module.llm_stats
        assert result.model == "llama3.2"
