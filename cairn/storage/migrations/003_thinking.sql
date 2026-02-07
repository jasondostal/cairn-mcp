-- Cairn: Thinking sequences
-- Migration 003: Structured reasoning tables for Phase 4

-- Thinking sequences: goal-oriented reasoning chains
CREATE TABLE IF NOT EXISTS thinking_sequences (
    id              SERIAL PRIMARY KEY,
    project_id      INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    goal            TEXT NOT NULL,
    status          VARCHAR(20) DEFAULT 'active',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);

-- Thoughts: individual reasoning steps within a sequence
CREATE TABLE IF NOT EXISTS thoughts (
    id              SERIAL PRIMARY KEY,
    sequence_id     INTEGER REFERENCES thinking_sequences(id) ON DELETE CASCADE,
    thought_type    VARCHAR(50) DEFAULT 'general',
    content         TEXT NOT NULL,
    branch_name     VARCHAR(255),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_thinking_sequences_project ON thinking_sequences (project_id);
CREATE INDEX IF NOT EXISTS idx_thinking_sequences_status ON thinking_sequences (status);
CREATE INDEX IF NOT EXISTS idx_thoughts_sequence ON thoughts (sequence_id, created_at);
