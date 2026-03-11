-- Migration 050: Remove deprecated tasks and cairns tables (ca-243)
--
-- Tasks replaced by work_items (v0.47.0).
-- Cairns replaced by orient() + temporal graph queries (v0.37.0).

DROP TABLE IF EXISTS task_memory_links;
DROP TABLE IF EXISTS tasks;
DROP TABLE IF EXISTS cairns;
