"""Core endpoints — status, settings."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Path

from cairn.config import (
    EDITABLE_KEYS,
    EXPERIMENTAL_CAPABILITIES,
    PROFILE_PRESETS,
    apply_overrides,
    config_to_flat,
    env_values,
)
from cairn.core.services import Services
from cairn.storage import settings_store

logger = logging.getLogger(__name__)

_VALID_LLM_BACKENDS = {"ollama", "bedrock", "gemini", "openai"}
_VALID_RERANKER_BACKENDS = {"local", "bedrock"}
_VALID_TERMINAL_BACKENDS = {"native", "ttyd", "disabled"}

_SECRET_SETTINGS = {
    "db.password", "auth.api_key", "auth.jwt_secret",
    "terminal.encryption_key",
    "llm.gemini_api_key", "llm.openai_api_key",
    "embedding.openai_api_key", "neo4j.password",
    "workspace.password", "oidc.client_secret",
}


def register_routes(router: APIRouter, svc: Services, **kw):
    from cairn.core.status import get_status

    db = svc.db
    config = svc.config
    env_snapshot = env_values()

    def _build_settings_response():
        """Build the settings response with values, sources, and editable info."""
        flat = config_to_flat(config)

        for key in _SECRET_SETTINGS:
            if key in flat and flat[key]:
                flat[key] = "••••••••"

        try:
            db_overrides = settings_store.load_all(db)
        except Exception:
            db_overrides = {}

        sources: dict[str, str] = {}
        for key in flat:
            if key in db_overrides:
                sources[key] = "db"
            elif env_snapshot.get(key) is not None:
                sources[key] = "env"
            else:
                sources[key] = "default"

        pending_restart = False
        if db_overrides:
            running_flat = config_to_flat(config)
            from cairn.server import _base_config
            hypothetical = apply_overrides(_base_config, db_overrides)
            hypothetical_flat = config_to_flat(hypothetical)
            for key in db_overrides:
                if key in running_flat and key in hypothetical_flat:
                    if str(running_flat[key]) != str(hypothetical_flat[key]):
                        pending_restart = True
                        break

        env_locked = sorted(k for k in flat if env_snapshot.get(k) is not None)

        return {
            "values": flat,
            "sources": sources,
            "editable": sorted(EDITABLE_KEYS),
            "env_locked": env_locked,
            "experimental": sorted(f"capabilities.{c}" for c in EXPERIMENTAL_CAPABILITIES),
            "profiles": sorted(PROFILE_PRESETS.keys()),
            "active_profile": config.profile or None,
            "pending_restart": pending_restart,
        }

    @router.get("/status")
    def api_status():
        return get_status(db, config, graph_provider=svc.graph_provider)

    @router.get("/settings")
    def api_settings():
        return _build_settings_response()

    @router.patch("/settings")
    def api_settings_update(body: dict):
        from cairn.api.utils import require_admin
        err = require_admin()
        if err:
            return err

        if not body:
            raise HTTPException(status_code=400, detail="Request body is required")

        # Reject env-locked keys
        locked = [k for k in body if k in EDITABLE_KEYS and env_snapshot.get(k) is not None]
        if locked:
            raise HTTPException(409, f"Cannot override env-locked settings: {', '.join(sorted(locked))}")

        errors = []
        updates: dict[str, str] = {}

        for key, value in body.items():
            if key not in EDITABLE_KEYS:
                errors.append(f"Key '{key}' is not editable")
                continue

            str_value = str(value).strip()

            if key == "llm.backend" and str_value not in _VALID_LLM_BACKENDS:
                errors.append(f"llm.backend must be one of: {', '.join(sorted(_VALID_LLM_BACKENDS))}")
                continue
            if key == "reranker.backend" and str_value not in _VALID_RERANKER_BACKENDS:
                errors.append(f"reranker.backend must be one of: {', '.join(sorted(_VALID_RERANKER_BACKENDS))}")
                continue
            if key == "terminal.backend" and str_value not in _VALID_TERMINAL_BACKENDS:
                errors.append(f"terminal.backend must be one of: {', '.join(sorted(_VALID_TERMINAL_BACKENDS))}")
                continue

            if key in ("reranker.candidates", "analytics.retention_days",
                       "terminal.max_sessions", "terminal.connect_timeout",
                       "ingest_chunk_size", "ingest_chunk_overlap"):
                try:
                    n = int(str_value)
                    if n < 1:
                        errors.append(f"{key} must be a positive integer")
                        continue
                except ValueError:
                    errors.append(f"{key} must be a valid integer")
                    continue

            if key in ("analytics.cost_embedding_per_1k", "analytics.cost_llm_input_per_1k",
                       "analytics.cost_llm_output_per_1k"):
                try:
                    f = float(str_value)
                    if f < 0:
                        errors.append(f"{key} must be non-negative")
                        continue
                except ValueError:
                    errors.append(f"{key} must be a valid number")
                    continue

            if key.startswith("capabilities.") or key in ("analytics.enabled", "auth.enabled", "enrichment_enabled"):
                str_value = "true" if str(value).lower() in ("true", "1", "yes") else "false"

            updates[key] = str_value

        if errors:
            raise HTTPException(status_code=400, detail="; ".join(errors))

        settings_store.save_bulk(db, updates)

        if svc.event_bus:
            from cairn.core.user import current_user as _current_user
            ctx = _current_user()
            svc.event_bus.emit(
                "settings.updated",
                actor="rest",
                payload={
                    "user": ctx.username if ctx else "anonymous",
                    "changes": {k: updates[k] for k in updates},
                },
            )

        return _build_settings_response()

    @router.delete("/settings/{key:path}")
    def api_settings_delete(key: str = Path(...)):
        if key not in EDITABLE_KEYS:
            raise HTTPException(status_code=400, detail=f"Key '{key}' is not editable")
        deleted = settings_store.delete(db, key)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"No override found for '{key}'")

        if svc.event_bus:
            from cairn.core.user import current_user as _current_user
            ctx = _current_user()
            svc.event_bus.emit(
                "settings.deleted",
                actor="rest",
                payload={
                    "user": ctx.username if ctx else "anonymous",
                    "key": key,
                },
            )

        return _build_settings_response()
