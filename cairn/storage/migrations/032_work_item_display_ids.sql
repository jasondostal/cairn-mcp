-- Migration 032: Work item display IDs
-- Replace hex-based short_id (wi-002a) with project-scoped sequential IDs (ca-42)
-- Adds work_item_prefix + work_item_next_seq to projects, seq_num to work_items
-- Drops short_id column (clean break)

-- 1. Add prefix columns to projects
ALTER TABLE projects ADD COLUMN IF NOT EXISTS work_item_prefix VARCHAR(10);
ALTER TABLE projects ADD COLUMN IF NOT EXISTS work_item_next_seq INTEGER DEFAULT 1;

-- 2. Add seq_num to work_items
ALTER TABLE work_items ADD COLUMN IF NOT EXISTS seq_num INTEGER;

-- 3. Backfill prefixes: lowercase first 2 chars, collision avoidance
DO $$
DECLARE
    r RECORD;
    candidate TEXT;
    base_name TEXT;
    prefix_len INT;
    suffix INT;
BEGIN
    FOR r IN SELECT id, name FROM projects ORDER BY
        (SELECT COUNT(*) FROM work_items WHERE project_id = projects.id) DESC, id
    LOOP
        -- Special-case __global__
        IF r.name = '__global__' THEN
            candidate := 'gl';
        ELSE
            base_name := lower(regexp_replace(r.name, '[^a-zA-Z0-9]', '', 'g'));
            IF base_name = '' THEN
                base_name := 'p' || r.id;
            END IF;
            candidate := left(base_name, 2);
        END IF;

        -- Check collision and try progressively longer prefixes
        prefix_len := 2;
        WHILE EXISTS(SELECT 1 FROM projects WHERE work_item_prefix = candidate AND id != r.id) LOOP
            prefix_len := prefix_len + 1;
            IF prefix_len <= length(base_name) THEN
                candidate := left(base_name, prefix_len);
            ELSE
                -- Numeric suffix fallback
                suffix := 1;
                candidate := left(base_name, 2) || suffix;
                WHILE EXISTS(SELECT 1 FROM projects WHERE work_item_prefix = candidate AND id != r.id) LOOP
                    suffix := suffix + 1;
                    candidate := left(base_name, 2) || suffix;
                END LOOP;
                EXIT;
            END IF;
        END LOOP;

        UPDATE projects SET work_item_prefix = candidate WHERE id = r.id;
    END LOOP;
END $$;

-- 4. Add unique constraint on work_item_prefix (nullable — projects without prefix can be NULL)
ALTER TABLE projects ADD CONSTRAINT uq_projects_work_item_prefix UNIQUE (work_item_prefix);

-- 5. Backfill seq_num: ROW_NUMBER() OVER (PARTITION BY project_id ORDER BY created_at, id)
UPDATE work_items wi SET seq_num = sub.rn
FROM (
    SELECT id, ROW_NUMBER() OVER (PARTITION BY project_id ORDER BY created_at, id) AS rn
    FROM work_items
) sub
WHERE wi.id = sub.id;

-- 6. Set work_item_next_seq on each project to MAX(seq_num) + 1
UPDATE projects p SET work_item_next_seq = COALESCE(sub.max_seq, 0) + 1
FROM (
    SELECT project_id, MAX(seq_num) AS max_seq
    FROM work_items
    GROUP BY project_id
) sub
WHERE p.id = sub.project_id;

-- 7. Add unique index on (project_id, seq_num)
CREATE UNIQUE INDEX IF NOT EXISTS idx_work_items_project_seq ON work_items (project_id, seq_num);

-- 8. Make seq_num NOT NULL
ALTER TABLE work_items ALTER COLUMN seq_num SET NOT NULL;

-- 9. Drop old short_id index and column
DROP INDEX IF EXISTS idx_work_items_short_id;
ALTER TABLE work_items DROP COLUMN IF EXISTS short_id;
