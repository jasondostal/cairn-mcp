-- Junction table: many-to-many link between sessions and work items.
-- Tracks which sessions touched which work items, with role escalation.

CREATE TABLE IF NOT EXISTS session_work_items (
    id              SERIAL PRIMARY KEY,
    session_name    VARCHAR(255) NOT NULL,
    work_item_id    INTEGER NOT NULL REFERENCES work_items(id) ON DELETE CASCADE,
    role            VARCHAR(30) NOT NULL DEFAULT 'touch',
    first_seen      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    touch_count     INTEGER NOT NULL DEFAULT 1,
    UNIQUE (session_name, work_item_id)
);

-- No FK on session_name: sessions row may not exist yet when link is created.

CREATE INDEX IF NOT EXISTS idx_swi_session_last
    ON session_work_items (session_name, last_seen DESC);

CREATE INDEX IF NOT EXISTS idx_swi_work_item_last
    ON session_work_items (work_item_id, last_seen DESC);
