-- Migration 014: Add author field for speaker attribution.
-- Tracks who created the memory: "user", "assistant", "system", or a specific name.
ALTER TABLE memories ADD COLUMN IF NOT EXISTS author VARCHAR(100);
