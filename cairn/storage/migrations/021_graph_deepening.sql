-- Cairn v0.44.0: Graph Deepening
-- Adds graph sync columns to thinking_sequences, thoughts, and tasks
-- for eventual-consistency dual-write to Neo4j.

-- Thinking sequences: graph sync tracking
ALTER TABLE thinking_sequences ADD COLUMN IF NOT EXISTS graph_uuid UUID;
ALTER TABLE thinking_sequences ADD COLUMN IF NOT EXISTS graph_synced BOOLEAN DEFAULT false;

-- Thoughts: graph sync tracking
ALTER TABLE thoughts ADD COLUMN IF NOT EXISTS graph_uuid UUID;
ALTER TABLE thoughts ADD COLUMN IF NOT EXISTS graph_synced BOOLEAN DEFAULT false;

-- Tasks: graph sync tracking
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS graph_uuid UUID;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS graph_synced BOOLEAN DEFAULT false;

-- Partial indexes for repair sweep (only unsynced rows)
CREATE INDEX IF NOT EXISTS idx_thinking_sequences_unsynced
    ON thinking_sequences (graph_synced) WHERE graph_synced = false;
CREATE INDEX IF NOT EXISTS idx_thoughts_unsynced
    ON thoughts (graph_synced) WHERE graph_synced = false;
CREATE INDEX IF NOT EXISTS idx_tasks_unsynced
    ON tasks (graph_synced) WHERE graph_synced = false;
