-- App settings: DB-persisted overrides for configuration values.
-- Resolution order: dataclass default -> env var -> DB override (highest priority).
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
