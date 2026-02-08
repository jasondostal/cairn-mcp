"""Migrate data from Recallium to Cairn.

Connects to Recallium's PostgreSQL (source) and Cairn's PostgreSQL (target),
transfers projects, memories, thinking sequences, thoughts, project links,
and related files. Embeddings are regenerated using Cairn's MiniLM-L6-v2.

Usage:
    python scripts/migrate_recallium.py [--dry-run]

Environment variables (or edit defaults below):
    RECALLIUM_DSN   - Recallium DB connection string
    CAIRN_DSN       - Cairn DB connection string
"""

import argparse
import json
import sys
import os

import psycopg


# ---------------------------------------------------------------------------
# Connection defaults
# ---------------------------------------------------------------------------
RECALLIUM_DSN = os.getenv("RECALLIUM_DSN")
CAIRN_DSN = os.getenv("CAIRN_DSN")

if not RECALLIUM_DSN or not CAIRN_DSN:
    print("ERROR: Set RECALLIUM_DSN and CAIRN_DSN environment variables.")
    print("  RECALLIUM_DSN=postgresql://user:pass@host:port/dbname")
    print("  CAIRN_DSN=postgresql://user:pass@host:port/dbname")
    sys.exit(1)

# Memory type mapping: Recallium → Cairn
TYPE_MAP = {
    "working-notes": "note",
    "general": "note",
    # project_brief/prd/plan get extracted to project_documents, not memories
}

# Types that become project_documents instead of memories
DOC_TYPES = {
    "project_brief": "brief",
    "project_prd": "prd",
    "project_plan": "plan",
}


def connect(dsn: str, label: str) -> psycopg.Connection:
    print(f"  Connecting to {label}...")
    conn = psycopg.connect(dsn, autocommit=False)
    print(f"  Connected to {label}.")
    return conn


def migrate_projects(src, dst) -> dict[int, int]:
    """Migrate projects. Returns {old_id: new_id} mapping."""
    rows = src.execute(
        "SELECT id, name, created_at, updated_at FROM projects ORDER BY id"
    ).fetchall()

    id_map = {}
    for r in rows:
        old_id, name, created_at, updated_at = r
        # Upsert — __global__ may already exist in Cairn
        result = dst.execute(
            """
            INSERT INTO projects (name, created_at, updated_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (name) DO UPDATE SET updated_at = EXCLUDED.updated_at
            RETURNING id
            """,
            (name, created_at, updated_at),
        ).fetchone()
        id_map[old_id] = result[0]

    print(f"  Projects: {len(id_map)} migrated")
    return id_map


def migrate_memories(src, dst, project_map: dict[int, int], embed_fn) -> dict[int, int]:
    """Migrate memories. Returns {old_id: new_id} mapping."""
    rows = src.execute(
        """
        SELECT m.id, m.content, m.summary, m.memory_type, m.importance_score,
               m.project_id, m.smart_tags, m.created_at, m.updated_at,
               m.is_active, m.inactivation_reason,
               m.related_memory_ids,
               s.session_name
        FROM memories m
        LEFT JOIN sessions s ON m.session_id = s.id
        WHERE m.is_active = true
        ORDER BY m.id
        """
    ).fetchall()

    id_map = {}
    doc_count = 0
    mem_count = 0

    for r in rows:
        (old_id, content, summary, mtype, importance, project_id,
         smart_tags, created_at, updated_at, is_active, inactive_reason,
         related_memory_ids, session_name) = r

        new_project_id = project_map.get(project_id)
        if new_project_id is None:
            print(f"    SKIP memory {old_id}: unknown project_id {project_id}")
            continue

        # Project documents go to project_documents table
        if mtype in DOC_TYPES:
            doc_type = DOC_TYPES[mtype]
            dst.execute(
                """
                INSERT INTO project_documents (project_id, doc_type, content, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (new_project_id, doc_type, content, created_at, updated_at),
            )
            doc_count += 1
            continue

        # Map memory type
        cairn_type = TYPE_MAP.get(mtype, mtype)
        tags = smart_tags or []

        # Generate embedding
        embedding = embed_fn(content)

        result = dst.execute(
            """
            INSERT INTO memories
                (content, summary, memory_type, importance, project_id, session_name,
                 embedding, tags, auto_tags, is_active, inactive_reason,
                 created_at, updated_at)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s::vector, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                content, summary, cairn_type, importance, new_project_id, session_name,
                str(embedding), tags, [], is_active, inactive_reason,
                created_at, updated_at,
            ),
        ).fetchone()
        id_map[old_id] = result[0]
        mem_count += 1

        if mem_count % 50 == 0:
            print(f"    ...{mem_count} memories embedded and inserted")

    print(f"  Memories: {mem_count} migrated, {doc_count} project docs extracted")
    return id_map


def migrate_related_files(src, dst, memory_map: dict[int, int]):
    """Copy related file paths from Recallium's memory_code_files into Cairn's related_files array."""
    rows = src.execute(
        "SELECT memory_id, array_agg(file_path) FROM memory_code_files GROUP BY memory_id"
    ).fetchall()

    count = 0
    for old_mem_id, files in rows:
        new_mem_id = memory_map.get(old_mem_id)
        if new_mem_id is None:
            continue
        dst.execute(
            "UPDATE memories SET related_files = %s WHERE id = %s",
            (files, new_mem_id),
        )
        count += 1

    print(f"  Related files: {count} memories updated")


def migrate_memory_relations(src, dst, memory_map: dict[int, int]):
    """Migrate related_memory_ids from Recallium's JSONB to Cairn's memory_relations table."""
    rows = src.execute(
        """
        SELECT id, related_memory_ids FROM memories
        WHERE related_memory_ids IS NOT NULL AND related_memory_ids != '[]'
        AND is_active = true
        """
    ).fetchall()

    count = 0
    for old_id, related_json in rows:
        new_source = memory_map.get(old_id)
        if new_source is None:
            continue
        related_ids = json.loads(related_json) if isinstance(related_json, str) else related_json
        for old_target in related_ids:
            new_target = memory_map.get(old_target)
            if new_target is None:
                continue
            dst.execute(
                """
                INSERT INTO memory_relations (source_id, target_id)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING
                """,
                (new_source, new_target),
            )
            count += 1

    print(f"  Memory relations: {count} links created")


def migrate_project_links(src, dst, project_map: dict[int, int]):
    """Migrate project-to-project links."""
    rows = src.execute(
        "SELECT source_project_id, target_project_id, link_type FROM project_links"
    ).fetchall()

    count = 0
    for src_pid, tgt_pid, link_type in rows:
        new_src = project_map.get(src_pid)
        new_tgt = project_map.get(tgt_pid)
        if new_src is None or new_tgt is None:
            continue
        dst.execute(
            """
            INSERT INTO project_links (source_id, target_id, link_type)
            VALUES (%s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (new_src, new_tgt, link_type),
        )
        count += 1

    print(f"  Project links: {count} migrated")


def migrate_thinking(src, dst, project_map: dict[int, int]):
    """Migrate thinking sequences and thoughts."""
    seqs = src.execute(
        """
        SELECT ts.id, ts.project_id, ts.goal, ts.is_complete,
               ts.completion_summary, ts.created_at
        FROM thinking_sequences ts
        ORDER BY ts.id
        """
    ).fetchall()

    seq_map = {}
    for old_id, project_id, goal, is_complete, completion_summary, created_at in seqs:
        new_project_id = project_map.get(project_id)
        if new_project_id is None:
            continue
        # Use goal, fall back to sequence_name via a separate query if goal is empty
        effective_goal = goal or "(migrated from Recallium)"
        status = "completed" if is_complete else "active"
        result = dst.execute(
            """
            INSERT INTO thinking_sequences (project_id, goal, status, created_at)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (new_project_id, effective_goal, status, created_at),
        ).fetchone()
        seq_map[old_id] = result[0]

    # Migrate thoughts
    thoughts = src.execute(
        """
        SELECT t.sequence_id, t.thought_type, t.content, t.created_at
        FROM thoughts t
        ORDER BY t.sequence_id, t.created_at
        """
    ).fetchall()

    thought_count = 0
    for seq_id, thought_type, content, created_at in thoughts:
        new_seq_id = seq_map.get(seq_id)
        if new_seq_id is None:
            continue
        dst.execute(
            """
            INSERT INTO thoughts (sequence_id, thought_type, content, created_at)
            VALUES (%s, %s, %s, %s)
            """,
            (new_seq_id, thought_type, content, created_at),
        )
        thought_count += 1

    print(f"  Thinking: {len(seq_map)} sequences, {thought_count} thoughts migrated")


def main():
    parser = argparse.ArgumentParser(description="Migrate Recallium data to Cairn")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without writing")
    args = parser.parse_args()

    print("=" * 60)
    print("Recallium → Cairn Migration")
    print("=" * 60)

    # Initialize embedding engine (uses Cairn's model)
    print("\nLoading embedding model (MiniLM-L6-v2)...")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("all-MiniLM-L6-v2")
    def embed(text: str) -> list[float]:
        return model.encode(text).tolist()
    print("Embedding model ready.")

    # Connect to databases
    print("\nConnecting to databases...")
    src_conn = connect(RECALLIUM_DSN, "Recallium (source)")
    dst_conn = connect(CAIRN_DSN, "Cairn (target)")

    if args.dry_run:
        # Just count what would be migrated
        count = src_conn.execute("SELECT count(*) FROM memories WHERE is_active = true").fetchone()[0]
        proj = src_conn.execute("SELECT count(*) FROM projects").fetchone()[0]
        print(f"\n  DRY RUN: Would migrate {proj} projects, {count} memories")
        src_conn.close()
        dst_conn.close()
        return

    try:
        print("\n--- Migrating Projects ---")
        project_map = migrate_projects(src_conn, dst_conn)

        print("\n--- Migrating Memories (with re-embedding) ---")
        memory_map = migrate_memories(src_conn, dst_conn, project_map, embed)

        print("\n--- Migrating Related Files ---")
        migrate_related_files(src_conn, dst_conn, memory_map)

        print("\n--- Migrating Memory Relations ---")
        migrate_memory_relations(src_conn, dst_conn, memory_map)

        print("\n--- Migrating Project Links ---")
        migrate_project_links(src_conn, dst_conn, project_map)

        print("\n--- Migrating Thinking Sequences ---")
        migrate_thinking(src_conn, dst_conn, project_map)

        dst_conn.commit()
        print("\n" + "=" * 60)
        print("Migration complete. All changes committed.")
        print("=" * 60)

    except Exception as e:
        dst_conn.rollback()
        print(f"\nERROR: {e}")
        print("All changes rolled back.")
        raise
    finally:
        src_conn.close()
        dst_conn.close()


if __name__ == "__main__":
    main()
