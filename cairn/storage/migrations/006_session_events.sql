-- Cairn: Event Pipeline v2 — streaming event batches with LLM digests
-- Migration 006: Session events table for CAPTURE → SHIP → DIGEST → CRYSTALLIZE pipeline

CREATE TABLE IF NOT EXISTS session_events (
    id              SERIAL PRIMARY KEY,
    project_id      INTEGER REFERENCES projects(id),
    session_name    VARCHAR(255) NOT NULL,
    batch_number    INTEGER NOT NULL,
    raw_events      JSONB NOT NULL,
    event_count     INTEGER NOT NULL DEFAULT 0,
    digest          TEXT,                           -- LLM-generated batch summary (null = undigested)
    digested_at     TIMESTAMPTZ,                    -- when digest was generated
    created_at      TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(project_id, session_name, batch_number)
);

-- DigestWorker polls for undigested batches
CREATE INDEX IF NOT EXISTS idx_session_events_undigested
    ON session_events (created_at ASC)
    WHERE digest IS NULL;

-- Cairn crystallization: fetch all batches for a session in order
CREATE INDEX IF NOT EXISTS idx_session_events_session
    ON session_events (project_id, session_name, batch_number);
