-- 051_unified_events.sql — Unified event architecture
-- Adds actor + span_id to events, widens event_type for tool/llm/embed events.

ALTER TABLE events ADD COLUMN IF NOT EXISTS actor VARCHAR(20) DEFAULT 'system';
ALTER TABLE events ADD COLUMN IF NOT EXISTS span_id VARCHAR(16);

-- Widen event_type from VARCHAR(50) to VARCHAR(100) for longer tool/llm types
ALTER TABLE events ALTER COLUMN event_type TYPE VARCHAR(100);

-- Update NOTIFY trigger to include actor
CREATE OR REPLACE FUNCTION notify_event() RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify('cairn_events', json_build_object(
        'id', NEW.id,
        'session_name', NEW.session_name,
        'event_type', NEW.event_type,
        'tool_name', NEW.tool_name,
        'work_item_id', NEW.work_item_id,
        'actor', NEW.actor,
        'created_at', NEW.created_at
    )::text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
