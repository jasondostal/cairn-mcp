-- Living Memory: consolidation tracking + beliefs foundation.

-- 1. Consolidation tracking — link demoted memories to their synthesized parent.
ALTER TABLE memories ADD COLUMN IF NOT EXISTS consolidated_into INTEGER REFERENCES memories(id);
CREATE INDEX IF NOT EXISTS idx_memories_consolidated
    ON memories (consolidated_into) WHERE consolidated_into IS NOT NULL;

-- 2. Beliefs — durable epistemic state with confidence and provenance.
CREATE TABLE IF NOT EXISTS beliefs (
    id              SERIAL PRIMARY KEY,
    project_id      INTEGER NOT NULL REFERENCES projects(id),
    agent_name      VARCHAR(255),
    content         TEXT NOT NULL,
    domain          VARCHAR(100),
    confidence      REAL NOT NULL DEFAULT 0.7,
    evidence_ids    INTEGER[] DEFAULT '{}',
    provenance      VARCHAR(50) DEFAULT 'crystallized',
    superseded_by   INTEGER REFERENCES beliefs(id),
    status          VARCHAR(20) DEFAULT 'active',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_beliefs_project
    ON beliefs (project_id, status, confidence DESC);
CREATE INDEX IF NOT EXISTS idx_beliefs_agent
    ON beliefs (agent_name, status) WHERE agent_name IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_beliefs_domain
    ON beliefs (domain, status) WHERE domain IS NOT NULL;
