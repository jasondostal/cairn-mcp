-- Bi-temporal support: event_at (when it happened) + valid_until (when it stopped being true).
-- created_at serves as transaction time (when we learned it). These add valid time.

ALTER TABLE memories ADD COLUMN IF NOT EXISTS event_at TIMESTAMPTZ;
ALTER TABLE memories ADD COLUMN IF NOT EXISTS valid_until TIMESTAMPTZ;

-- Index for temporal queries: "what happened between X and Y?"
CREATE INDEX IF NOT EXISTS idx_memories_event_at
    ON memories (event_at)
    WHERE event_at IS NOT NULL AND is_active = true;

-- Index for validity queries: "what's still current?"
CREATE INDEX IF NOT EXISTS idx_memories_valid_until
    ON memories (valid_until)
    WHERE valid_until IS NOT NULL AND is_active = true;
