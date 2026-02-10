-- Migration 008: Ingestion pipeline support
-- Adds ingestion_log for dedup/tracking and source_doc_id for chunk→doc linkage.

-- Ingestion log for dedup and tracking
CREATE TABLE IF NOT EXISTS ingestion_log (
    id          SERIAL PRIMARY KEY,
    source      TEXT,
    project_id  INTEGER REFERENCES projects(id),
    content_hash VARCHAR(64) NOT NULL,
    target_type VARCHAR(20) NOT NULL,
    target_ids  INTEGER[] DEFAULT '{}',
    chunk_count INTEGER DEFAULT 1,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ingestion_dedup
    ON ingestion_log(content_hash);

-- Link chunks back to source document
ALTER TABLE memories
    ADD COLUMN IF NOT EXISTS source_doc_id INTEGER REFERENCES project_documents(id);
CREATE INDEX IF NOT EXISTS idx_memories_source_doc
    ON memories(source_doc_id) WHERE source_doc_id IS NOT NULL;
