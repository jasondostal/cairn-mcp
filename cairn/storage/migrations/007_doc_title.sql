-- Migration 007: Add title column to project_documents
ALTER TABLE project_documents ADD COLUMN IF NOT EXISTS title VARCHAR(255);
