-- Event dispatch tracking for subscriber framework.
-- Each event × handler pair gets a dispatch record for reliable delivery with retry.

CREATE TABLE IF NOT EXISTS event_dispatches (
    id              BIGSERIAL PRIMARY KEY,
    event_id        BIGINT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    handler         VARCHAR(100) NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'pending',
    attempts        INT NOT NULL DEFAULT 0,
    last_error      TEXT,
    next_retry      TIMESTAMPTZ DEFAULT NOW(),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    UNIQUE(event_id, handler)
);

-- Partial index for the dispatcher poll query: only pending/failed dispatches.
CREATE INDEX IF NOT EXISTS idx_dispatches_pending
    ON event_dispatches (next_retry)
    WHERE status IN ('pending', 'failed');
