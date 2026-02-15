"""One-time entity deduplication script for Neo4j knowledge graph.

Finds duplicate entities (case-insensitive name match), merges them into
canonical entities (the one with the most statements wins), and handles
identity fragmentation (e.g. multiple name variants for the same person).

Run with --dry-run first (default), validate, then --execute.

Usage:
    python -m cairn.scripts.dedup_entities [--dry-run] [--project PROJECT]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict

from cairn.config import load_config
from cairn.graph.config import Neo4jConfig
from cairn.graph.neo4j_provider import Neo4jGraphProvider

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Known identity aliases — merge these into a single canonical entity.
# Add project-specific alias groups as needed before running.
IDENTITY_ALIASES: list[list[str]] = [
    # Example: ["user", "User", "John", "John Smith"]
    # Populated by inspecting the graph before running.
]


def get_entity_statement_counts(driver, database: str) -> dict[str, int]:
    """Count statements per entity UUID."""
    with driver.session(database=database) as session:
        result = session.run(
            """
            MATCH (e:Entity)
            OPTIONAL MATCH (e)-[:SUBJECT|OBJECT]-(s:Statement)
            RETURN e.uuid AS uuid, e.name AS name, e.entity_type AS entity_type,
                   e.project_id AS project_id, count(s) AS stmt_count
            ORDER BY e.name
            """
        )
        return {
            r["uuid"]: {
                "name": r["name"],
                "entity_type": r["entity_type"],
                "project_id": r["project_id"],
                "stmt_count": r["stmt_count"],
            }
            for r in result
        }


def find_duplicate_groups(entities: dict) -> list[list[str]]:
    """Group entities by case-insensitive name within the same project."""
    by_key: dict[tuple, list[str]] = defaultdict(list)
    for uuid, info in entities.items():
        key = (info["name"].lower().strip(), info["project_id"])
        by_key[key].append(uuid)

    # Only return groups with >1 entity
    return [uuids for uuids in by_key.values() if len(uuids) > 1]


def find_alias_groups(entities: dict, alias_lists: list[list[str]]) -> list[list[str]]:
    """Find entities matching alias groups (identity fragmentation)."""
    groups = []
    for aliases in alias_lists:
        alias_set = {a.lower().strip() for a in aliases}
        matching_uuids = [
            uuid for uuid, info in entities.items()
            if info["name"].lower().strip() in alias_set
        ]
        if len(matching_uuids) > 1:
            groups.append(matching_uuids)
    return groups


def pick_canonical(uuids: list[str], entities: dict) -> tuple[str, list[str]]:
    """Pick canonical entity (most statements). Return (canonical_uuid, duplicate_uuids)."""
    sorted_by_count = sorted(uuids, key=lambda u: entities[u]["stmt_count"], reverse=True)
    return sorted_by_count[0], sorted_by_count[1:]


def merge_entities(provider: Neo4jGraphProvider, canonical_id: str, duplicate_ids: list[str],
                   entities: dict, dry_run: bool) -> int:
    """Merge duplicates into canonical. Returns number of merges performed."""
    canonical = entities[canonical_id]
    merged = 0
    for dup_id in duplicate_ids:
        dup = entities[dup_id]
        if dry_run:
            logger.info(
                "  [DRY RUN] Would merge '%s' (%s, %d stmts) -> '%s' (%s, %d stmts)",
                dup["name"], dup["entity_type"], dup["stmt_count"],
                canonical["name"], canonical["entity_type"], canonical["stmt_count"],
            )
        else:
            try:
                result = provider.merge_entities(canonical_id, dup_id)
                logger.info(
                    "  Merged '%s' -> '%s' (moved %d subject + %d object edges)",
                    dup["name"], canonical["name"],
                    result["subject_edges_moved"], result["object_edges_moved"],
                )
                merged += 1
            except Exception:
                logger.error("  Failed to merge '%s' -> '%s'", dup["name"], canonical["name"], exc_info=True)
    return merged


def main():
    parser = argparse.ArgumentParser(description="Deduplicate Neo4j entities")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Only show what would be done (default: true)")
    parser.add_argument("--execute", action="store_true",
                        help="Actually perform the merges")
    parser.add_argument("--project", type=int, default=None,
                        help="Filter to specific project_id")
    parser.add_argument("--aliases-file", type=str, default=None,
                        help="JSON file with alias groups: [[\"name1\", \"name2\"], ...]")
    args = parser.parse_args()

    dry_run = not args.execute

    config = load_config()
    provider = Neo4jGraphProvider(config.neo4j)
    provider.connect()

    try:
        logger.info("Fetching all entities...")
        entities = get_entity_statement_counts(provider._driver, provider._db)
        logger.info("Found %d entities", len(entities))

        if args.project:
            entities = {u: e for u, e in entities.items() if e["project_id"] == args.project}
            logger.info("Filtered to %d entities for project_id=%d", len(entities), args.project)

        # Load alias groups
        alias_lists = list(IDENTITY_ALIASES)
        if args.aliases_file:
            with open(args.aliases_file) as f:
                alias_lists.extend(json.load(f))

        # Phase 1: Case-insensitive name duplicates
        dup_groups = find_duplicate_groups(entities)
        logger.info("Found %d duplicate groups (case-insensitive name match)", len(dup_groups))

        total_merged = 0
        for group in dup_groups:
            canonical_id, dup_ids = pick_canonical(group, entities)
            canonical = entities[canonical_id]
            logger.info(
                "Group: '%s' (%d entities) — canonical: %s (%d stmts)",
                canonical["name"], len(group), canonical_id, canonical["stmt_count"],
            )
            total_merged += merge_entities(provider, canonical_id, dup_ids, entities, dry_run)

        # Phase 2: Identity alias groups
        alias_groups = find_alias_groups(entities, alias_lists)
        if alias_groups:
            logger.info("Found %d alias groups", len(alias_groups))
            for group in alias_groups:
                canonical_id, dup_ids = pick_canonical(group, entities)
                canonical = entities[canonical_id]
                names = [entities[u]["name"] for u in group]
                logger.info(
                    "Alias group: %s — canonical: '%s' (%d stmts)",
                    names, canonical["name"], canonical["stmt_count"],
                )
                total_merged += merge_entities(provider, canonical_id, dup_ids, entities, dry_run)

        action = "Would merge" if dry_run else "Merged"
        logger.info("%s %d entities total", action, total_merged)
        if dry_run:
            logger.info("Run with --execute to apply changes")

    finally:
        provider.close()


if __name__ == "__main__":
    main()
