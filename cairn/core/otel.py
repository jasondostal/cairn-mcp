"""OpenTelemetry bridge — exports spans to OTLP endpoint.

Zero cost when disabled or when opentelemetry packages are not installed.
Reads trace context from Phase 1 (cairn.core.trace) and exports as OTel spans.

Usage:
    from cairn.core import otel
    otel.init(config.otel)          # at startup
    otel.export_span(...)           # after each operation
    otel.shutdown()                 # at shutdown
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cairn.config import OTelConfig

logger = logging.getLogger(__name__)

_ENABLED = False
_tracer = None
_provider = None  # TracerProvider, cached at init for shutdown
_StatusCode = None  # opentelemetry.trace.StatusCode, cached at init


def init(config: OTelConfig) -> None:
    """Initialize OTel if enabled and packages are available."""
    global _ENABLED, _tracer, _provider, _StatusCode

    if not config.enabled:
        return

    if not config.endpoint:
        logger.warning("OTel enabled but no endpoint configured (CAIRN_OTEL_ENDPOINT). Skipping.")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.trace import StatusCode
    except ImportError:
        logger.warning(
            "OTel enabled but opentelemetry packages not installed. "
            "Install with: pip install cairn[otel]"
        )
        return

    try:
        resource = Resource.create({"service.name": config.service_name})
        _provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=f"{config.endpoint}/v1/traces")
        _provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(_provider)
        _tracer = trace.get_tracer("cairn", schema_url=None)
        _StatusCode = StatusCode
        _ENABLED = True
        logger.info(
            "OTel export enabled: endpoint=%s, service=%s",
            config.endpoint, config.service_name,
        )
    except Exception:
        logger.warning("OTel initialization failed", exc_info=True)


def export_span(
    operation: str,
    duration_ms: float,
    success: bool,
    tokens_in: int = 0,
    tokens_out: int = 0,
    project_id: str | None = None,
    model: str | None = None,
    error_message: str | None = None,
) -> None:
    """Export a completed operation as an OTel span.

    No-op when OTel is disabled or not initialized.
    """
    if not _ENABLED or _tracer is None:
        return

    try:
        # Read trace context from Phase 1
        from cairn.core.trace import current_trace
        ctx = current_trace()

        span = _tracer.start_span(
            name=operation,
            start_time=int((time.time() - duration_ms / 1000) * 1e9),
        )

        # Set attributes
        span.set_attribute("cairn.operation", operation)
        span.set_attribute("cairn.success", success)
        span.set_attribute("cairn.duration_ms", duration_ms)
        if tokens_in:
            span.set_attribute("cairn.tokens.input", tokens_in)
        if tokens_out:
            span.set_attribute("cairn.tokens.output", tokens_out)
        if project_id:
            span.set_attribute("cairn.project_id", project_id)
        if model:
            span.set_attribute("cairn.model", model)

        # Trace context from Phase 1
        if ctx:
            span.set_attribute("cairn.trace_id", ctx.trace_id)
            if ctx.actor:
                span.set_attribute("cairn.actor", ctx.actor)
            if ctx.entry_point:
                span.set_attribute("cairn.entry_point", ctx.entry_point)

        if _StatusCode is not None:
            if success:
                span.set_status(_StatusCode.OK)
            else:
                span.set_status(_StatusCode.ERROR, error_message or "operation failed")
                if error_message:
                    span.set_attribute("cairn.error", error_message)

        span.end(end_time=int(time.time() * 1e9))

    except Exception:
        # Never let OTel export errors affect core operations
        logger.debug("OTel span export failed", exc_info=True)


def shutdown() -> None:
    """Flush and shut down the tracer provider."""
    global _ENABLED, _tracer, _provider

    if not _ENABLED:
        return

    try:
        if _provider is not None and hasattr(_provider, "shutdown"):
            _provider.shutdown()
        logger.info("OTel export shutdown complete")
    except Exception:
        logger.debug("OTel shutdown failed", exc_info=True)
    finally:
        _ENABLED = False
        _tracer = None
        _provider = None


def is_enabled() -> bool:
    """Check if OTel export is active."""
    return _ENABLED
