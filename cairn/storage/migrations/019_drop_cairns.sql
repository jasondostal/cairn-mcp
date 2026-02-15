-- v0.37.0: Drop cairns infrastructure.
-- The trail() tool and temporal graph queries replace cairn-based boot orientation.
-- session_name on memories is preserved (still useful for temporal clustering).
-- session_events table stays (still useful for event pipeline).

-- Drop cairn FK from memories (keep session_name — it's still useful)
ALTER TABLE memories DROP COLUMN IF EXISTS cairn_id;

-- Drop cairns table
DROP TABLE IF EXISTS cairns;
