-- Migration 010: Analytics — usage tracking and pre-aggregated rollups
-- Raw event log for all MCP tool invocations + hourly aggregates for dashboards.

-- Raw usage events (one row per MCP tool call)
CREATE TABLE IF NOT EXISTS usage_events (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
    operation VARCHAR(64) NOT NULL,
    project_id INTEGER REFERENCES projects(id),
    session_name VARCHAR(256),
    tokens_in INTEGER NOT NULL DEFAULT 0,
    tokens_out INTEGER NOT NULL DEFAULT 0,
    latency_ms REAL NOT NULL DEFAULT 0,
    model VARCHAR(128),
    success BOOLEAN NOT NULL DEFAULT true,
    error_message TEXT,
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_usage_events_timestamp
    ON usage_events (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_usage_events_operation_ts
    ON usage_events (operation, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_usage_events_project_ts
    ON usage_events (project_id, timestamp DESC);

-- Pre-aggregated hourly rollups
CREATE TABLE IF NOT EXISTS metric_rollups (
    id BIGSERIAL PRIMARY KEY,
    bucket_hour TIMESTAMPTZ NOT NULL,
    operation VARCHAR(64) NOT NULL,
    project_id INTEGER REFERENCES projects(id),
    op_count INTEGER NOT NULL DEFAULT 0,
    error_count INTEGER NOT NULL DEFAULT 0,
    tokens_in_sum BIGINT NOT NULL DEFAULT 0,
    tokens_out_sum BIGINT NOT NULL DEFAULT 0,
    latency_p50 REAL,
    latency_p95 REAL,
    latency_p99 REAL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_metric_rollups_unique
    ON metric_rollups (bucket_hour, operation, COALESCE(project_id, 0));

CREATE INDEX IF NOT EXISTS idx_metric_rollups_bucket
    ON metric_rollups (bucket_hour DESC);
CREATE INDEX IF NOT EXISTS idx_metric_rollups_operation_bucket
    ON metric_rollups (operation, bucket_hour DESC);

-- Watermark tracking for rollup worker
CREATE TABLE IF NOT EXISTS rollup_state (
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    last_event_id BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO rollup_state (id, last_event_id) VALUES (1, 0) ON CONFLICT DO NOTHING;
