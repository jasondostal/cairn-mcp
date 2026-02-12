-- Migration 012: Add entities column for entity extraction
-- Entities are extracted by the LLM enrichment pipeline (people, places, orgs, projects).
-- Stored as TEXT[] with GiN index, same pattern as tags.

ALTER TABLE memories ADD COLUMN IF NOT EXISTS entities TEXT[] DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_memories_entities_gin ON memories USING GIN (entities);
