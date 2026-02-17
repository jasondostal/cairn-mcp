-- 025_event_bus.sql — Lightweight event bus tables
-- Replaces JSONB-batch session_events with individual event rows + Postgres NOTIFY.
-- session_events left in place (no longer read by application code).

-- Lightweight sessions table (replaces session_events for lifecycle)
CREATE TABLE IF NOT EXISTS sessions (
    id              SERIAL PRIMARY KEY,
    session_name    VARCHAR(255) UNIQUE NOT NULL,
    project_id      INTEGER REFERENCES projects(id),
    agent_id        VARCHAR(255),
    agent_type      VARCHAR(50) DEFAULT 'interactive',
    parent_session  VARCHAR(255),
    started_at      TIMESTAMPTZ DEFAULT NOW(),
    closed_at       TIMESTAMPTZ,
    metadata        JSONB DEFAULT '{}'
);

-- Individual event rows (replaces session_events.raw_events JSONB batches)
CREATE TABLE IF NOT EXISTS events (
    id              BIGSERIAL PRIMARY KEY,
    session_name    VARCHAR(255) NOT NULL,
    agent_id        VARCHAR(255),
    work_item_id    INTEGER REFERENCES work_items(id),
    project_id      INTEGER REFERENCES projects(id),
    event_type      VARCHAR(50) NOT NULL,
    tool_name       VARCHAR(100),
    payload         JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_events_session ON events (session_name, created_at);
CREATE INDEX IF NOT EXISTS idx_events_work_item ON events (work_item_id, created_at) WHERE work_item_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_events_type ON events (event_type, created_at);

-- Postgres NOTIFY trigger for real-time streaming
CREATE OR REPLACE FUNCTION notify_event() RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify('cairn_events', json_build_object(
        'id', NEW.id,
        'session_name', NEW.session_name,
        'event_type', NEW.event_type,
        'tool_name', NEW.tool_name,
        'work_item_id', NEW.work_item_id,
        'created_at', NEW.created_at
    )::text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER events_notify
    AFTER INSERT ON events
    FOR EACH ROW EXECUTE FUNCTION notify_event();
