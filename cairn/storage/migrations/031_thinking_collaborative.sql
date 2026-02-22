-- Cairn: Collaborative thinking
-- Migration 031: Add author attribution and sequence reopening

-- Who contributed each thought (NULL = agent for backwards compat)
ALTER TABLE thoughts ADD COLUMN IF NOT EXISTS author VARCHAR(100);

-- Track when a completed sequence was reopened
ALTER TABLE thinking_sequences ADD COLUMN IF NOT EXISTS reopened_at TIMESTAMPTZ;
