CREATE TABLE IF NOT EXISTS document_attachments (
    id          SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES project_documents(id) ON DELETE CASCADE,
    filename    VARCHAR(255) NOT NULL,
    mime_type   VARCHAR(127) NOT NULL,
    size_bytes  INTEGER NOT NULL,
    data        BYTEA NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_doc_attachments_document
    ON document_attachments (document_id);
