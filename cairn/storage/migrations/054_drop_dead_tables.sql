-- 054: Drop dead tables from agent infrastructure removal (v0.80.0 memory-slim)
--
-- Tables dropped because all code using them was removed:
--   alerting, audit, chat, conversations, deliverables,
--   sessions, terminal, webhooks, workspace, subscriptions,
--   notifications, retention, agent_memory

DROP TABLE IF EXISTS alert_history CASCADE;
DROP TABLE IF EXISTS alert_rules CASCADE;
DROP TABLE IF EXISTS audit_log CASCADE;
DROP TABLE IF EXISTS chat_messages CASCADE;
DROP TABLE IF EXISTS conversations CASCADE;
DROP TABLE IF EXISTS deliverables CASCADE;
DROP TABLE IF EXISTS event_subscriptions CASCADE;
DROP TABLE IF EXISTS notifications CASCADE;
DROP TABLE IF EXISTS retention_policies CASCADE;
DROP TABLE IF EXISTS session_events CASCADE;
DROP TABLE IF EXISTS session_work_items CASCADE;
DROP TABLE IF EXISTS sessions CASCADE;
DROP TABLE IF EXISTS ssh_hosts CASCADE;
DROP TABLE IF EXISTS webhook_deliveries CASCADE;
DROP TABLE IF EXISTS webhooks CASCADE;
DROP TABLE IF EXISTS workspace_sessions CASCADE;
DROP TABLE IF EXISTS agent_learnings CASCADE;
DROP TABLE IF EXISTS working_memory_deprecated CASCADE;
