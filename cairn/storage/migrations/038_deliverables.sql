-- Migration 038: Deliverables — structured agent output for human review
-- Part of ca-136 Human/Agent Collaboration & Multi-Agent Orchestration

CREATE TABLE deliverables (
    id SERIAL PRIMARY KEY,
    work_item_id INTEGER NOT NULL REFERENCES work_items(id) ON DELETE CASCADE,
    version INTEGER NOT NULL DEFAULT 1,
    status VARCHAR(20) NOT NULL DEFAULT 'draft',
    summary TEXT NOT NULL DEFAULT '',
    changes JSONB NOT NULL DEFAULT '[]',
    decisions JSONB NOT NULL DEFAULT '[]',
    open_items JSONB NOT NULL DEFAULT '[]',
    metrics JSONB NOT NULL DEFAULT '{}',
    reviewer_notes TEXT,
    reviewed_by VARCHAR(255),
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_deliverables_work_item ON deliverables (work_item_id);
CREATE INDEX idx_deliverables_status ON deliverables (status);
CREATE INDEX idx_deliverables_created ON deliverables (created_at DESC);
CREATE UNIQUE INDEX idx_deliverables_work_item_version ON deliverables (work_item_id, version);
