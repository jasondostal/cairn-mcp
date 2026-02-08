-- Cairn: Episodic memory (cairns)
-- Migration 004: Session markers that stack stones into a navigable trail

-- Cairns (episodes): stones stacked by session
CREATE TABLE IF NOT EXISTS cairns (
    id              SERIAL PRIMARY KEY,
    project_id      INTEGER REFERENCES projects(id),
    session_name    VARCHAR(255),                   -- links to memories.session_name
    title           TEXT,                           -- LLM-generated or manual
    narrative       TEXT,                           -- LLM-synthesized session summary
    events          JSONB,                          -- ordered session events (hook-captured, optional)
    memory_count    INTEGER DEFAULT 0,
    started_at      TIMESTAMPTZ DEFAULT NOW(),
    set_at          TIMESTAMPTZ,                    -- when the cairn was "set" (concluded)
    is_compressed   BOOLEAN DEFAULT false,          -- events cleared, narrative persists

    UNIQUE(project_id, session_name)
);

-- Link stones to their cairn
ALTER TABLE memories ADD COLUMN IF NOT EXISTS cairn_id INTEGER REFERENCES cairns(id);

-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_cairns_project ON cairns (project_id);
CREATE INDEX IF NOT EXISTS idx_cairns_set_at ON cairns (set_at DESC);
CREATE INDEX IF NOT EXISTS idx_memories_cairn ON memories (cairn_id);
