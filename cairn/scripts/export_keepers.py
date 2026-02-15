#!/usr/bin/env python3
"""Export curated keeper memories and project documents from Cairn.

For the v0.37.0 fresh production start. Exports:
- Explicitly curated memory IDs (relationship, design, infra, etc.)
- ALL rule-type memories (behavioral guardrails)
- ALL project documents (primers, guides, writeups, etc.)
- Project metadata

Usage:
    python3 export_keepers.py [--api-base http://localhost:8000/api] [--output /path/to/output.json]
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime

# ── Curated keeper memory IDs ──────────────────────────────────────────────

KEEPER_IDS = {
    # ── Category 1: The Relationship / Arc ──
    20,   # The Compact — sparring partnership agreement
    48,   # Graduation flow — trust progression
    75,   # Collaboration evolution Phase 0→5 (part 1)
    76,   # Collaboration evolution Phase 0→5 (part 2)
    99,   # Motes organic metaphor origin
    116,  # The Third Voice — Kristin review insight
    131,  # Emotional arc documentation
    132,  # Vulnerability fear — "seen as stupid"
    134,  # Shower thoughts session
    135,  # Captain Crunch — hacker ethos moment
    177,  # What IS this relationship
    255,  # ADHD-informed, GRIMOIRE portable
    257,  # ADHD cognitive scaffolding realization
    416,  # The Arc of Jason Dostal — full reflection
    671,  # The test that mattered — tears of relief

    # ── Category 3: Design Preferences ──
    29,   # Feel → Terminology translation
    50,   # Build empirical design system
    56,   # UI preferences — MiniMe admin style
    85,   # CurioCraft admin baseline
    93,   # Motes inception — polymorphic design system
    278,  # 2-column settings grid pattern
    320,  # Design philosophy evolution
    530,  # Design system — base theme
    624,  # Cairn UI as new design standard

    # ── Category 4: Architecture Decisions ──
    419,  # Project birth: Cairn naming
    502,  # Cairn metaphor as architecture
    503,  # Motes → Cairn → Stones thread
    599,  # Motes architecture assembled organically
    650,  # Neo4j + knowledge architecture decision
    653,  # Final v2 architecture decision
    684,  # Drop stones/cairns metaphor — everything is a node
    685,  # v0.37.0 implementation complete
    686,  # Fresh production start decision
    687,  # Letter to the next instance

    # ── Category 5: Infrastructure Reference ──
    35,   # Project portfolio
    49,   # Recallium deployment status
    53,   # Home automation stack — full picture
    189,  # Homelab infrastructure audit (January)
    190,  # Service inventory — Authentik/auth mapping
    192,  # Infrastructure details — IPs, DNS, domains
    193,  # Homelab documentation migration (Bookstack → markdown)
    197,  # Homelab deep dive session — SWAG, auth, IoT
    198,  # SWAG nginx patterns — internal locations, auto-auth
    200,  # Markdown to PDF conversion (md-to-pdf)
    201,  # Key homelab files modified — proxy confs, docs
    211,  # Docker static IP scheme
    315,  # Home Assistant configuration deep dive
    391,  # Irrigation controller v2 — ESPHome
    394,  # ESPHome project kickoff
    395,  # Hardware notes — sensors, relays, valves
    400,  # SWAG auto-reload behavior
    401,  # Dev server role
    403,  # Two-server architecture
    524,  # Docker network rule — homelab network
    525,  # Rule: backup nginx configs before editing
    554,  # Infrastructure audit February 2026
    559,  # Garage valet automation suite
    591,  # Cairn production deploy workflow
    609,  # MCP server configuration across IDEs

    # ── Category 6: Document/Primer memories ──
    107,  # FDX API specification reference
    114,  # EVOLUTION.md tone feedback from Kristin
    118,  # Kristin review session — close the loop
    119,  # Capability brief session
    127,  # Evolution thesis — vulnerability as barrier
    136,  # EIS/EIP roadmap + manifesto
    256,  # FDX fundamentals document
    294,  # SYSTEMS_PRIMER.md created
    374,  # FastAPI/Scoreline primer created
    411,  # Bedrock setup + MCP primer
    413,  # Semantic systems primer session
    414,  # SEMANTIC_SYSTEMS_PRIMER.md written
    417,  # THE_ARC.md published + Builder's Foundations
    464,  # Cairn eval framework
    466,  # Eval tests — 40 passing
    609,  # MCP server config across IDEs (research)
    616,  # Tool descriptions as agent UX
    651,  # RedPlanetHQ/core architecture analysis

    # ── Category 7: Key Project memories ──
    105,  # FDX thinking sequence (paused)
    180,  # CurioCraft as living design lab
    240,  # Scoreline — full vibe coding + trust milestone
    287,  # Scoreline v1.0.0 release
    319,  # Birdsong project born
    323,  # Birdsong build session
    366,  # Scoreline v1.2.0 release

    # ── Category 8: Additional keepers ──
    242,  # Trust level update — full operational autonomy
    309,  # Datasette deployment experiment (BirdNET)
    471,  # Recallium → Cairn migration complete
    529,  # Rule: Kristin reviews external content (may be caught by rules query too)
    565,  # Cairn deploy workflow
    669,  # MCP connection fix (v0.34.2)
    672,  # v0.35.0 release + knowledge extraction
    678,  # Cairn v0.36 vision — agent workspace
    679,  # v0.36.0 workspace architecture reference
    683,  # Nonprod DB setup, agent config, v0.36.1
}


# ── API helpers ────────────────────────────────────────────────────────────

def api_get(base_url: str, path: str):
    """GET request to Cairn API. Returns parsed JSON or None on error."""
    url = f"{base_url}{path}"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"  WARNING: HTTP {e.code} fetching {path}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  WARNING: {e} fetching {path}", file=sys.stderr)
        return None


def fetch_all_rule_ids(base_url: str) -> list[int]:
    """Fetch IDs of ALL rule-type memories."""
    result = api_get(base_url, "/timeline?type=rule&limit=200")
    if not result:
        return []
    return [m["id"] for m in result.get("items", [])]


def fetch_memory(base_url: str, memory_id: int) -> dict | None:
    """Fetch a single memory with full content via recall endpoint."""
    return api_get(base_url, f"/memories/{memory_id}")


def fetch_projects(base_url: str) -> list[dict]:
    """Fetch all projects."""
    result = api_get(base_url, "/projects")
    if not result:
        return []
    return result.get("items", [])


def fetch_project_detail(base_url: str, name: str) -> dict | None:
    """Fetch project docs and links."""
    return api_get(base_url, f"/projects/{name}")


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Export keeper memories from Cairn")
    parser.add_argument(
        "--api-base",
        default="http://localhost:8000/api",
        help="Cairn API base URL (default: http://localhost:8000/api)",
    )
    parser.add_argument(
        "--output",
        default="v037-keepers.json",
        help="Output JSON file path (default: ./v037-keepers.json)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  Cairn Keeper Export — v0.37.0 Fresh Start")
    print("=" * 60)
    print(f"  API: {args.api_base}")
    print(f"  Output: {args.output}")
    print()

    # ── Step 1: Collect all keeper IDs ──
    print("[1/4] Collecting keeper IDs...")
    rule_ids = fetch_all_rule_ids(args.api_base)
    print(f"  Rules (dynamic): {len(rule_ids)} found")
    print(f"  Curated IDs: {len(KEEPER_IDS)}")

    all_ids = KEEPER_IDS | set(rule_ids)
    print(f"  Total unique: {len(all_ids)}")
    print()

    # ── Step 2: Fetch each memory ──
    print(f"[2/4] Fetching {len(all_ids)} memories...")
    memories = []
    failed = []
    for i, mid in enumerate(sorted(all_ids), 1):
        mem = fetch_memory(args.api_base, mid)
        if mem:
            # Tag with category for import reference
            cats = []
            if mid in {20, 48, 75, 76, 99, 116, 131, 132, 134, 135, 177, 255, 257, 416, 671}:
                cats.append("relationship")
            if mem.get("memory_type") == "rule":
                cats.append("rule")
            if mid in {29, 50, 56, 85, 93, 278, 320, 530, 624}:
                cats.append("design")
            if mid in {419, 502, 503, 599, 650, 653, 684, 685, 686, 687}:
                cats.append("architecture")
            if mid in {49, 53, 189, 190, 192, 193, 197, 198, 200, 201, 211, 315,
                        391, 394, 395, 400, 401, 403, 524, 525, 554, 559, 591, 609}:
                cats.append("infrastructure")
            if mid in {107, 114, 118, 119, 127, 136, 256, 294, 374, 411, 413, 414,
                        417, 464, 466, 616, 651}:
                cats.append("document")
            if mid in {35, 105, 180, 240, 287, 319, 323, 366}:
                cats.append("project")
            mem["_keeper_categories"] = cats
            memories.append(mem)
        else:
            failed.append(mid)

        if i % 25 == 0 or i == len(all_ids):
            print(f"  {i}/{len(all_ids)} fetched...")

    print(f"  OK: {len(memories)} memories")
    if failed:
        print(f"  FAILED: {len(failed)} IDs: {sorted(failed)}")
    print()

    # ── Step 3: Fetch projects and documents ──
    print("[3/4] Fetching projects and documents...")
    projects = fetch_projects(args.api_base)
    print(f"  Projects: {len(projects)}")

    all_docs = []
    for proj in projects:
        name = proj["name"]
        detail = fetch_project_detail(args.api_base, name)
        if detail and "docs" in detail:
            for doc in detail["docs"]:
                doc["project"] = name
                all_docs.append(doc)

    print(f"  Documents: {len(all_docs)}")
    print()

    # ── Step 4: Build and write export ──
    print("[4/4] Writing export...")

    # Sort memories by original created_at for chronological import
    memories.sort(key=lambda m: m.get("created_at", ""))

    export = {
        "export_version": "1.0",
        "export_date": datetime.utcnow().isoformat() + "Z",
        "source": "production backup",
        "cairn_version": "0.37.0",
        "purpose": "Curated keeper memories for v0.37.0 fresh production start",
        "stats": {
            "total_memories": len(memories),
            "total_documents": len(all_docs),
            "total_projects": len(projects),
            "failed_ids": sorted(failed),
            "categories": {
                "relationship": sum(1 for m in memories if "relationship" in m.get("_keeper_categories", [])),
                "rule": sum(1 for m in memories if "rule" in m.get("_keeper_categories", [])),
                "design": sum(1 for m in memories if "design" in m.get("_keeper_categories", [])),
                "architecture": sum(1 for m in memories if "architecture" in m.get("_keeper_categories", [])),
                "infrastructure": sum(1 for m in memories if "infrastructure" in m.get("_keeper_categories", [])),
                "document": sum(1 for m in memories if "document" in m.get("_keeper_categories", [])),
                "project": sum(1 for m in memories if "project" in m.get("_keeper_categories", [])),
            },
        },
        "projects": projects,
        "memories": memories,
        "documents": all_docs,
    }

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(export, f, indent=2, default=str)

    size_mb = os.path.getsize(args.output) / (1024 * 1024)

    print()
    print("=" * 60)
    print("  Export complete!")
    print("=" * 60)
    print(f"  File: {args.output}")
    print(f"  Size: {size_mb:.2f} MB")
    print(f"  Memories: {len(memories)} ({len(failed)} failed)")
    print(f"  Documents: {len(all_docs)}")
    print(f"  Projects: {len(projects)}")
    print()

    # Category breakdown
    print("  Category breakdown:")
    for cat, count in export["stats"]["categories"].items():
        print(f"    {cat}: {count}")


if __name__ == "__main__":
    main()
