#!/usr/bin/env python3
"""Import keeper memories and project documents into a fresh Cairn instance.

Reads the export JSON from export_keepers.py and re-ingests via the REST API.
Memories go through the full v0.37.0 pipeline (enrichment, knowledge extraction).
Caller-specified fields (importance, tags, memory_type, author) are preserved.

After import, --preserve-dates patches created_at back to original timestamps
via direct Postgres UPDATE, restoring the full temporal ordering.

Usage:
    python3 import_keepers.py [--api-base http://localhost:8000/api] [--input /path/to/keepers.json]
    python3 import_keepers.py --dry-run   # preview without importing
    python3 import_keepers.py --preserve-dates  # restore original timestamps after import
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error

# Postgres connection for --preserve-dates
# Postgres connection defaults — override via env vars
PG_HOST = os.environ.get("CAIRN_PG_HOST", "localhost")
PG_PORT = os.environ.get("CAIRN_PG_PORT", "5432")
PG_DB = os.environ.get("CAIRN_PG_DB", "cairn")
PG_USER = os.environ.get("CAIRN_PG_USER", "cairn")
PG_PASS = os.environ.get("CAIRN_PG_PASS", "cairn-dev-password")


def api_post(base_url: str, path: str, data: dict) -> dict | None:
    """POST JSON to Cairn API."""
    url = f"{base_url}{path}"
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")[:200]
        print(f"  ERROR {e.code}: {error_body}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  ERROR: {e}", file=sys.stderr)
        return None


def api_get(base_url: str, path: str) -> dict | None:
    """GET from Cairn API."""
    url = f"{base_url}{path}"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"  ERROR: {e}", file=sys.stderr)
        return None


def import_memory(base_url: str, mem: dict) -> dict | None:
    """Import a single memory via the ingest endpoint."""
    # Resolve project name
    project = mem.get("project")
    if isinstance(project, dict):
        project = project.get("name", "__global__")
    if not project:
        project = "__global__"

    payload = {
        "content": mem["content"],
        "project": project,
        "memory_type": mem.get("memory_type", "note"),
        "importance": mem.get("importance", 0.5),
        "tags": mem.get("tags", []),
        "session_name": mem.get("session_name"),
        "related_files": mem.get("related_files", []),
    }

    # Preserve author if set
    if mem.get("author"):
        payload["author"] = mem["author"]

    return api_post(base_url, "/ingest/memory", payload)


def preserve_dates(
    id_map: dict[int, int],
    memories: list[dict],
    db_container: str = "cairn-db",
) -> tuple[int, int]:
    """Patch created_at back to original timestamps via Postgres.

    Uses docker exec to run psql inside the database container,
    since psql may not be installed on the host.

    Returns (patched, failed) counts.
    """
    # Build old_id -> original created_at lookup
    date_lookup = {}
    for mem in memories:
        old_id = mem.get("id")
        created_at = mem.get("created_at")
        if old_id and created_at:
            date_lookup[old_id] = created_at

    # Build a single SQL batch for efficiency
    sql_statements = []
    mapping_count = 0
    for old_id, new_id in id_map.items():
        old_id_int = int(old_id) if isinstance(old_id, str) else old_id
        original_date = date_lookup.get(old_id_int)
        if not original_date:
            continue
        sql_statements.append(
            f"UPDATE memories SET created_at = '{original_date}' WHERE id = {new_id};"
        )
        mapping_count += 1

    if not sql_statements:
        return 0, len(id_map)

    # Execute as a single batch via docker exec
    batch_sql = "\n".join(sql_statements)
    try:
        result = subprocess.run(
            [
                "docker", "exec", "-i", db_container,
                "psql", "-U", PG_USER, "-d", PG_DB,
            ],
            input=batch_sql,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            print(f"    psql batch error: {result.stderr.strip()}", file=sys.stderr)
            return 0, mapping_count

        # Count successful UPDATEs
        patched = result.stdout.count("UPDATE 1")
        failed = mapping_count - patched
        return patched, failed

    except Exception as e:
        print(f"    Error running psql batch: {e}", file=sys.stderr)
        return 0, mapping_count


def import_document(base_url: str, doc: dict) -> dict | None:
    """Import a project document via the ingest endpoint."""
    payload = {
        "project": doc["project"],
        "doc_type": doc.get("doc_type", "brief"),
        "content": doc["content"],
    }
    if doc.get("title"):
        payload["title"] = doc["title"]

    return api_post(base_url, "/ingest/doc", payload)


def main():
    parser = argparse.ArgumentParser(description="Import keeper memories into fresh Cairn")
    parser.add_argument(
        "--api-base",
        default="http://localhost:8000/api",
        help="Cairn API base URL (default: http://localhost:8000/api)",
    )
    parser.add_argument(
        "--input",
        default="v037-keepers.json",
        help="Input JSON file from export_keepers.py (default: ./v037-keepers.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview import without actually ingesting",
    )
    parser.add_argument(
        "--skip-memories",
        action="store_true",
        help="Skip memory import (only import docs)",
    )
    parser.add_argument(
        "--skip-docs",
        action="store_true",
        help="Skip document import (only import memories)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay between memory imports in seconds (default: 1.0, allows enrichment/extraction)",
    )
    parser.add_argument(
        "--preserve-dates",
        action="store_true",
        help="After import, patch created_at back to original timestamps via Postgres",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  Cairn Keeper Import — v0.37.0 Fresh Start")
    print("=" * 60)

    # Load export
    print(f"  Input: {args.input}")
    with open(args.input) as f:
        export = json.load(f)

    memories = export.get("memories", [])
    documents = export.get("documents", [])
    stats = export.get("stats", {})

    print(f"  Memories: {len(memories)}")
    print(f"  Documents: {len(documents)}")
    print(f"  Export date: {export.get('export_date', 'unknown')}")
    print(f"  Source: {export.get('source', 'unknown')}")
    if args.dry_run:
        print("  MODE: DRY RUN (no changes)")
    print()

    # Check target is healthy
    if not args.dry_run:
        status = api_get(args.api_base, "/status")
        if not status:
            print("ERROR: Cannot reach target API. Is Cairn running?", file=sys.stderr)
            sys.exit(1)
        target_memories = status.get("memories", "?")
        print(f"  Target: {args.api_base}")
        print(f"  Target version: {status.get('version', '?')}")
        print(f"  Target memories: {target_memories}")
        print()

        if isinstance(target_memories, int) and target_memories > 10:
            print(f"  WARNING: Target already has {target_memories} memories!")
            resp = input("  Continue anyway? (y/N): ").strip().lower()
            if resp != "y":
                print("  Aborted.")
                sys.exit(0)

    # ── Import memories ──
    if not args.skip_memories:
        print(f"[1/2] Importing {len(memories)} memories...")
        id_map = {}  # old_id -> new_id
        imported = 0
        failed = 0

        for i, mem in enumerate(memories, 1):
            old_id = mem.get("id", "?")
            cats = mem.get("_keeper_categories", [])
            cat_str = ",".join(cats) if cats else "uncategorized"

            if args.dry_run:
                project = mem.get("project")
                if isinstance(project, dict):
                    project = project.get("name", "?")
                print(f"  [{i}/{len(memories)}] #{old_id} ({mem.get('memory_type', '?')}) "
                      f"[{cat_str}] project={project}")
                continue

            result = import_memory(args.api_base, mem)
            if result and "id" in result:
                new_id = result["id"]
                id_map[old_id] = new_id
                imported += 1
                if i % 10 == 0 or i == len(memories):
                    print(f"  {i}/{len(memories)} imported... (#{old_id} -> #{new_id})")
            else:
                failed += 1
                print(f"  FAILED #{old_id}: {mem.get('summary', '')[:60]}")

            # Throttle to let enrichment/extraction breathe
            if args.delay > 0 and not args.dry_run:
                time.sleep(args.delay)

        if not args.dry_run:
            print(f"  Imported: {imported}, Failed: {failed}")

            # Save ID mapping for reference
            map_path = args.input.replace(".json", "-id-map.json")
            with open(map_path, "w") as f:
                json.dump(id_map, f, indent=2)
            print(f"  ID mapping saved: {map_path}")
        print()

    # ── Preserve original timestamps ──
    if args.preserve_dates and not args.dry_run and not args.skip_memories and id_map:
        print("[DATE RESTORE] Patching created_at to original timestamps...")
        db_container = os.environ.get("CAIRN_DB_CONTAINER", "cairn-db")
        patched, date_failed = preserve_dates(id_map, memories, db_container)
        print(f"  Patched: {patched}, Failed: {date_failed}")

        # Verify with a spot check
        if id_map:
            first_old = list(id_map.keys())[0]
            first_new = id_map[first_old]
            check = subprocess.run(
                [
                    "docker", "exec", db_container,
                    "psql", "-U", PG_USER, "-d", PG_DB,
                    "-t", "-c", f"SELECT created_at FROM memories WHERE id = {first_new};",
                ],
                capture_output=True, text=True, timeout=10,
            )
            if check.returncode == 0:
                print(f"  Spot check: new #{first_new} (was #{first_old}) -> {check.stdout.strip()}")
        print()

    # ── Import documents ──
    if not args.skip_docs:
        print(f"[2/2] Importing {len(documents)} documents...")
        doc_imported = 0
        doc_failed = 0

        for i, doc in enumerate(documents, 1):
            project = doc.get("project", "?")
            title = doc.get("title", doc.get("doc_type", "?"))

            if args.dry_run:
                print(f"  [{i}/{len(documents)}] {project}/{doc.get('doc_type', '?')}: {title}")
                continue

            result = import_document(args.api_base, doc)
            if result:
                doc_imported += 1
                if i % 10 == 0 or i == len(documents):
                    print(f"  {i}/{len(documents)} imported...")
            else:
                doc_failed += 1
                print(f"  FAILED: {project}/{title}")

            # Small delay for docs too
            if args.delay > 0:
                time.sleep(args.delay * 0.5)

        if not args.dry_run:
            print(f"  Imported: {doc_imported}, Failed: {doc_failed}")
        print()

    # ── Summary ──
    print("=" * 60)
    if args.dry_run:
        print("  Dry run complete — no changes made")
        print(f"  Would import: {len(memories)} memories, {len(documents)} documents")
        if args.preserve_dates:
            print(f"  Would restore original timestamps on all memories")
    else:
        # Check final state
        final_status = api_get(args.api_base, "/status")
        if final_status:
            print(f"  Import complete!")
            print(f"  Final memory count: {final_status.get('memories', '?')}")
            if args.preserve_dates:
                print(f"  Original timestamps: RESTORED")
        else:
            print("  Import finished (could not verify final state)")
    print("=" * 60)


if __name__ == "__main__":
    main()
