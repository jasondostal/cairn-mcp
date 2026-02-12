"""One-off: export memories from a Cairn-compatible Postgres into eval/data/corpus.json.

Connects to a running PostgreSQL instance with the Cairn schema,
selects a diverse sample across projects/types, and writes the corpus file.

Usage:
    python -m eval.corpus_export
    python -m eval.corpus_export --limit 50 --port 5432
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

DATA_DIR = Path(__file__).parent / "data"


def export_memories(
    host: str = "localhost",
    port: int = 5432,
    dbname: str = "cairn",
    user: str = "cairn",
    password: str = "cairn-dev-password",
    limit: int = 50,
) -> dict:
    """Export a diverse sample of memories from a Cairn database.

    Selects across projects and memory types to get a representative corpus.
    """
    dsn = f"postgresql://{user}:{password}@{host}:{port}/{dbname}"

    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        # Get a diverse sample: order by project + type to spread across categories,
        # then take top N. This is better than random for eval purposes.
        rows = conn.execute("""
            SELECT
                m.id,
                m.content,
                m.memory_type,
                m.importance,
                m.tags,
                COALESCE(m.auto_tags, '{}') as auto_tags,
                m.session_name,
                p.name as project
            FROM memories m
            LEFT JOIN projects p ON m.project_id = p.id
            WHERE m.is_active = true
                AND m.content IS NOT NULL
                AND LENGTH(m.content) > 20
            ORDER BY
                p.name,
                m.memory_type,
                m.importance DESC
            LIMIT %s
        """, (limit,)).fetchall()

    memories = []
    for i, row in enumerate(rows, start=1):
        memories.append({
            "id": f"m{i:02d}",
            "content": row["content"],
            "memory_type": row["memory_type"],
            "importance": float(row["importance"]),
            "tags": row["tags"] or [],
            "auto_tags": row["auto_tags"] or [],
            "project": row["project"] or "general",
            "session_name": row["session_name"] or "",
        })

    return {
        "metadata": {
            "version": "1.0",
            "memory_count": len(memories),
            "exported_at": datetime.now().isoformat(),
        },
        "memories": memories,
    }


def main():
    parser = argparse.ArgumentParser(description="Export memories from Cairn database for eval corpus")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--dbname", default="cairn")
    parser.add_argument("--user", default="cairn")
    parser.add_argument("--password", default="cairn-dev-password")
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    print(f"Exporting up to {args.limit} memories from {args.host}:{args.port}/{args.dbname}...")

    try:
        corpus = export_memories(
            host=args.host,
            port=args.port,
            dbname=args.dbname,
            user=args.user,
            password=args.password,
            limit=args.limit,
        )
    except psycopg.OperationalError as e:
        print(f"Connection failed: {e}", file=sys.stderr)
        print("Is the Cairn database running on the expected port?", file=sys.stderr)
        sys.exit(1)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DATA_DIR / "corpus.json"
    out_path.write_text(json.dumps(corpus, indent=2, default=str))
    print(f"Exported {corpus['metadata']['memory_count']} memories to {out_path}")


if __name__ == "__main__":
    main()
