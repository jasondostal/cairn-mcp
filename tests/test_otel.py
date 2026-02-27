"""Tests for Watchtower Phase 6 — OpenTelemetry Export."""

from __future__ import annotations

from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from cairn.core import otel


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_config(enabled=False, endpoint="", service_name="cairn"):
    cfg = MagicMock()
    cfg.enabled = enabled
    cfg.endpoint = endpoint
    cfg.service_name = service_name
    return cfg


class _FakeStatusCode:
    """Stand-in for opentelemetry.trace.StatusCode when packages aren't installed."""
    OK = "OK"
    ERROR = "ERROR"


# ---------------------------------------------------------------------------
# Reset state between tests
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_otel():
    """Reset OTel module state before each test."""
    otel._ENABLED = False
    otel._tracer = None
    otel._provider = None
    otel._StatusCode = None
    yield
    otel._ENABLED = False
    otel._tracer = None
    otel._provider = None
    otel._StatusCode = None


# ===========================================================================
# Init
# ===========================================================================

class TestInit:
    def test_disabled_by_default(self):
        otel.init(_make_config(enabled=False))
        assert otel.is_enabled() is False

    def test_enabled_no_endpoint_warns(self):
        otel.init(_make_config(enabled=True, endpoint=""))
        assert otel.is_enabled() is False

    def test_enabled_missing_packages(self):
        """When OTel packages are not installed, init degrades gracefully."""
        with patch.dict("sys.modules", {"opentelemetry": None}):
            # Re-import to trigger ImportError path
            config = _make_config(enabled=True, endpoint="http://localhost:4318")
            otel.init(config)
            assert otel.is_enabled() is False

    @patch("cairn.core.otel.logger")
    def test_enabled_with_mock_packages(self, mock_logger):
        """When packages are available, init succeeds."""
        mock_provider = MagicMock()
        mock_tracer = MagicMock()

        with patch.dict("sys.modules", {
            "opentelemetry": MagicMock(),
            "opentelemetry.trace": MagicMock(),
            "opentelemetry.sdk": MagicMock(),
            "opentelemetry.sdk.trace": MagicMock(),
            "opentelemetry.sdk.trace.export": MagicMock(),
            "opentelemetry.sdk.resources": MagicMock(),
            "opentelemetry.exporter": MagicMock(),
            "opentelemetry.exporter.otlp": MagicMock(),
            "opentelemetry.exporter.otlp.proto": MagicMock(),
            "opentelemetry.exporter.otlp.proto.http": MagicMock(),
            "opentelemetry.exporter.otlp.proto.http.trace_exporter": MagicMock(),
        }):
            import importlib
            import cairn.core.otel as otel_mod
            # Manually call init with the mocks in place
            config = _make_config(enabled=True, endpoint="http://localhost:4318")
            otel_mod.init(config)
            assert otel_mod._ENABLED is True


# ===========================================================================
# Export span
# ===========================================================================

class TestExportSpan:
    def test_noop_when_disabled(self):
        """export_span is a no-op when OTel is disabled."""
        # Should not raise even with no setup
        otel.export_span(
            operation="test.op",
            duration_ms=100.0,
            success=True,
        )

    def test_export_when_enabled(self):
        """When enabled, export_span creates and finishes a span."""
        mock_span = MagicMock()
        mock_tracer = MagicMock()
        mock_tracer.start_span.return_value = mock_span

        otel._ENABLED = True
        otel._tracer = mock_tracer
        otel._StatusCode = _FakeStatusCode

        with patch("cairn.core.trace.current_trace") as mock_ctx:
            mock_ctx.return_value = None

            otel.export_span(
                operation="store",
                duration_ms=50.0,
                success=True,
                tokens_in=100,
                tokens_out=50,
                project_id="test-project",
                model="llama3",
            )

            mock_tracer.start_span.assert_called_once()
            # Verify attributes were set
            calls = mock_span.set_attribute.call_args_list
            attrs = {c[0][0]: c[0][1] for c in calls}
            assert attrs["cairn.operation"] == "store"
            assert attrs["cairn.success"] is True
            assert attrs["cairn.duration_ms"] == 50.0
            assert attrs["cairn.tokens.input"] == 100
            assert attrs["cairn.tokens.output"] == 50
            assert attrs["cairn.project_id"] == "test-project"
            assert attrs["cairn.model"] == "llama3"
            mock_span.end.assert_called_once()

    def test_export_with_trace_context(self):
        """Trace context from Phase 1 is included in span attributes."""
        mock_span = MagicMock()
        mock_tracer = MagicMock()
        mock_tracer.start_span.return_value = mock_span

        otel._ENABLED = True
        otel._tracer = mock_tracer
        otel._StatusCode = _FakeStatusCode

        mock_trace = MagicMock()
        mock_trace.trace_id = "abc-123"
        mock_trace.actor = "mcp"
        mock_trace.entry_point = "store"

        with patch("cairn.core.trace.current_trace", return_value=mock_trace):
            otel.export_span(
                operation="store",
                duration_ms=10.0,
                success=True,
            )

            calls = mock_span.set_attribute.call_args_list
            attrs = {c[0][0]: c[0][1] for c in calls}
            assert attrs["cairn.trace_id"] == "abc-123"
            assert attrs["cairn.actor"] == "mcp"
            assert attrs["cairn.entry_point"] == "store"

    def test_export_error_span(self):
        """Failed operations set ERROR status."""
        mock_span = MagicMock()
        mock_tracer = MagicMock()
        mock_tracer.start_span.return_value = mock_span

        otel._ENABLED = True
        otel._tracer = mock_tracer
        otel._StatusCode = _FakeStatusCode

        with patch("cairn.core.trace.current_trace", return_value=None):
            otel.export_span(
                operation="enrich",
                duration_ms=200.0,
                success=False,
                error_message="LLM timeout",
            )

            calls = mock_span.set_attribute.call_args_list
            attrs = {c[0][0]: c[0][1] for c in calls}
            assert attrs["cairn.success"] is False
            assert attrs["cairn.error"] == "LLM timeout"

    def test_export_error_does_not_propagate(self):
        """OTel export errors never affect core operations."""
        otel._ENABLED = True
        otel._tracer = MagicMock()
        otel._tracer.start_span.side_effect = RuntimeError("otel broken")

        # Should not raise
        otel.export_span(
            operation="store", duration_ms=10.0, success=True,
        )


# ===========================================================================
# Shutdown
# ===========================================================================

class TestShutdown:
    def test_shutdown_when_disabled(self):
        """Shutdown is a no-op when disabled."""
        otel.shutdown()  # Should not raise

    def test_shutdown_clears_state(self):
        """Shutdown resets module state."""
        mock_provider = MagicMock()
        otel._ENABLED = True
        otel._tracer = MagicMock()
        otel._provider = mock_provider

        otel.shutdown()

        mock_provider.shutdown.assert_called_once()
        assert otel._ENABLED is False
        assert otel._tracer is None
        assert otel._provider is None


# ===========================================================================
# is_enabled
# ===========================================================================

class TestIsEnabled:
    def test_false_by_default(self):
        assert otel.is_enabled() is False

    def test_true_when_set(self):
        otel._ENABLED = True
        assert otel.is_enabled() is True
