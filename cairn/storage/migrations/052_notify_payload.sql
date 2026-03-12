-- 052_notify_payload.sql — Include payload + project_id in NOTIFY for client-side metrics
-- SystemPulse UI consumes raw SSE events and does client-side aggregation.
-- Payload fields (tokens_in, tokens_out, latency_ms, success) are needed for EKG metrics.

CREATE OR REPLACE FUNCTION notify_event() RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify('cairn_events', json_build_object(
        'event_id', NEW.id,
        'session_name', NEW.session_name,
        'event_type', NEW.event_type,
        'tool_name', NEW.tool_name,
        'work_item_id', NEW.work_item_id,
        'actor', NEW.actor,
        'project_id', NEW.project_id,
        'payload', NEW.payload,
        'created_at', NEW.created_at
    )::text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
