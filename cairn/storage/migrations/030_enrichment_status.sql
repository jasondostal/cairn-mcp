-- Enrichment status tracking: enables detection and recovery of failed enrichment.
-- Values: pending | complete | partial | failed | none (enrich=False)

ALTER TABLE memories ADD COLUMN IF NOT EXISTS enrichment_status VARCHAR(20)
    NOT NULL DEFAULT 'pending';
ALTER TABLE memories ADD COLUMN IF NOT EXISTS enriched_at TIMESTAMPTZ;

-- Backfill from existing data
UPDATE memories SET enrichment_status = CASE
    WHEN entities != '{}' AND array_length(entities, 1) > 0 THEN 'complete'
    WHEN summary IS NOT NULL AND summary != '' THEN 'partial'
    ELSE 'none'
END, enriched_at = CASE
    WHEN entities != '{}' AND array_length(entities, 1) > 0 THEN updated_at
    ELSE NULL
END;

-- Index for finding memories that need re-enrichment
CREATE INDEX IF NOT EXISTS idx_memories_enrichment_status
    ON memories (enrichment_status)
    WHERE is_active = true AND enrichment_status IN ('pending', 'failed', 'none');
