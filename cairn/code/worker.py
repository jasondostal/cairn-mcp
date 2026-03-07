"""Standalone code intelligence worker.

Runs on the host where source code lives. Indexes codebases into Neo4j
and watches for changes. Designed to run independently of the main cairn
server — no MCP, no FastAPI, no event loop timeouts.

Connects to Neo4j directly for graph writes. Resolves project IDs via
the cairn REST API (avoids needing direct PostgreSQL access).

Usage:
    python -m cairn.code.worker \
        --neo4j-uri bolt://util:7687 \
        --cairn-url http://util:8081 \
        --watch /home/user/working/myproject:myproject \
        --watch /home/user/working/other:other

    # Or via env vars:
    CAIRN_NEO4J_URI=bolt://util:7687 \
    CAIRN_API_URL=http://util:8081 \
    CAIRN_CODE_PROJECTS="myproject=/home/user/working/myproject,other=/home/user/working/other" \
    python -m cairn.code.worker

Environment variables:
    CAIRN_NEO4J_URI         Neo4j bolt URI (default: bolt://localhost:7687)
    CAIRN_NEO4J_USER        Neo4j username (default: neo4j)
    CAIRN_NEO4J_PASSWORD    Neo4j password (default: cairn-dev-password)
    CAIRN_NEO4J_DATABASE    Neo4j database (default: neo4j)
    CAIRN_API_URL           Cairn server URL for project resolution (default: http://localhost:8000)
    CAIRN_API_KEY           API key for authenticated cairn instances (optional)
    CAIRN_CODE_PROJECTS     Comma-separated project=path pairs
    CAIRN_CODE_WATCH        Enable file watching (default: true)
    CAIRN_CODE_FORCE        Force re-index even if unchanged (default: false)
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("cairn.code.worker")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Cairn code intelligence worker — indexes and watches codebases.",
    )
    parser.add_argument(
        "--watch", "-w",
        action="append",
        metavar="PATH:PROJECT",
        help="Directory to index and watch, as path:project (repeatable)",
    )
    parser.add_argument(
        "--neo4j-uri",
        default=os.getenv("CAIRN_NEO4J_URI", "bolt://localhost:7687"),
    )
    parser.add_argument(
        "--neo4j-user",
        default=os.getenv("CAIRN_NEO4J_USER", "neo4j"),
    )
    parser.add_argument(
        "--neo4j-password",
        default=os.getenv("CAIRN_NEO4J_PASSWORD", "cairn-dev-password"),
    )
    parser.add_argument(
        "--neo4j-database",
        default=os.getenv("CAIRN_NEO4J_DATABASE", "neo4j"),
    )
    parser.add_argument(
        "--cairn-url",
        default=os.getenv("CAIRN_API_URL", "http://localhost:8000"),
        help="Cairn server URL for project resolution",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("CAIRN_API_KEY", ""),
        help="API key for authenticated cairn instances",
    )
    parser.add_argument("--force", action="store_true", default=os.getenv("CAIRN_CODE_FORCE", "false").lower() in ("true", "1"))
    parser.add_argument("--no-watch", action="store_true", default=os.getenv("CAIRN_CODE_WATCH", "true").lower() in ("false", "0"))
    return parser.parse_args()


def _parse_projects(args: argparse.Namespace) -> list[tuple[str, Path, int | None]]:
    """Build list of (project_name, directory_path, project_id) from args + env.

    Format: path:project or path:project:id
    Env: project=path or project=path:id
    """
    projects: list[tuple[str, Path, int | None]] = []

    # From --watch flags
    if args.watch:
        for spec in args.watch:
            if ":" not in spec:
                logger.error("Invalid --watch format %r, expected path:project[:id]", spec)
                sys.exit(1)
            parts = spec.rsplit(":", maxsplit=2)
            if len(parts) == 3:
                path_str, project, id_str = parts
                pid = int(id_str)
            elif len(parts) == 2:
                path_str, project = parts
                pid = None
            else:
                logger.error("Invalid --watch format %r", spec)
                sys.exit(1)
            p = Path(path_str).resolve()
            if not p.is_dir():
                logger.error("Not a directory: %s", p)
                sys.exit(1)
            projects.append((project, p, pid))

    # From CAIRN_CODE_PROJECTS env
    env_projects = os.getenv("CAIRN_CODE_PROJECTS", "")
    if env_projects:
        for pair in env_projects.split(","):
            pair = pair.strip()
            if not pair:
                continue
            if "=" not in pair:
                logger.error("Invalid CAIRN_CODE_PROJECTS format %r, expected project=path[:id]", pair)
                sys.exit(1)
            project, rest = pair.split("=", 1)
            if ":" in rest:
                path_str, id_str = rest.rsplit(":", 1)
                pid = int(id_str)
            else:
                path_str = rest
                pid = None
            p = Path(path_str).resolve()
            if not p.is_dir():
                logger.error("Not a directory: %s", p)
                sys.exit(1)
            projects.append((project.strip(), p, pid))

    if not projects:
        logger.error("No projects specified. Use --watch path:project[:id] or CAIRN_CODE_PROJECTS=project=path[:id]")
        sys.exit(1)

    return projects


def _resolve_project_id(
    cairn_url: str, project_name: str, api_key: str = "", graph: Any = None,
) -> int | None:
    """Resolve a project name to its numeric ID.

    Tries the cairn REST API first (GET /api/projects). Falls back to
    querying Neo4j for an existing project_id on CodeFile nodes.
    """
    import json
    import urllib.request

    headers: dict[str, str] = {}
    if api_key:
        headers["X-API-Key"] = api_key

    # Strategy 1: cairn REST API
    try:
        req = urllib.request.Request(f"{cairn_url}/api/projects", headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            if isinstance(data, list):
                for p in data:
                    if p.get("name") == project_name:
                        return p["id"]
    except Exception:
        logger.debug("API project lookup failed, trying Neo4j fallback", exc_info=True)

    # Strategy 2: Query Neo4j for existing project_id (from prior indexing)
    if graph:
        try:
            result = graph._run_query(
                "MATCH (cf:CodeFile) WHERE cf.project_id IS NOT NULL "
                "RETURN DISTINCT cf.project_id AS pid LIMIT 100"
            )
            # If only one project_id exists, use it
            pids = [r["pid"] for r in result]
            if len(pids) == 1:
                logger.info("Resolved %r to project_id %d from Neo4j (single project)", project_name, pids[0])
                return pids[0]
        except Exception:
            logger.debug("Neo4j project_id lookup failed", exc_info=True)

    # Strategy 3: Create via API
    try:
        body = json.dumps({"name": project_name}).encode()
        headers["Content-Type"] = "application/json"
        req = urllib.request.Request(
            f"{cairn_url}/api/projects", data=body, headers=headers, method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return data.get("id")
    except Exception:
        logger.warning("Failed to resolve project %r — API and Neo4j both failed", project_name, exc_info=True)

    return None


def main() -> None:
    args = _parse_args()
    projects = _parse_projects(args)

    logger.info("Cairn code worker starting")
    logger.info("Projects: %s", ", ".join(f"{name}={path}" for name, path, _ in projects))

    # Connect to Neo4j
    from cairn.config import Neo4jConfig
    from cairn.graph.neo4j_provider import Neo4jGraphProvider

    neo4j_config = Neo4jConfig(
        uri=args.neo4j_uri,
        user=args.neo4j_user,
        password=args.neo4j_password,
        database=args.neo4j_database,
    )
    graph = Neo4jGraphProvider(neo4j_config)
    graph.connect()
    graph.ensure_schema()
    logger.info("Neo4j connected: %s", args.neo4j_uri)

    # Resolve project IDs — use explicit IDs when provided, else try API/Neo4j
    project_ids: dict[str, int] = {}
    for name, _, explicit_id in projects:
        if explicit_id is not None:
            project_ids[name] = explicit_id
            logger.info("Project %r -> id %d (explicit)", name, explicit_id)
        else:
            pid = _resolve_project_id(args.cairn_url, name, api_key=args.api_key, graph=graph)
            if pid is None:
                logger.error("Failed to resolve project %r. Provide an explicit ID: path:project:ID", name)
                graph.close()
                sys.exit(1)
            project_ids[name] = pid
            logger.info("Project %r -> id %d (resolved)", name, pid)

    # Initial index
    from cairn.code.indexer import CodeIndexer
    from cairn.code.parser import CodeParser

    parser = CodeParser()
    indexer = CodeIndexer(parser, graph)

    for name, path, _ in projects:
        logger.info("Indexing %s at %s ...", name, path)
        t0 = time.monotonic()
        result = indexer.index_directory(
            root=path,
            project=name,
            project_id=project_ids[name],
            force=args.force,
        )
        elapsed = time.monotonic() - t0
        logger.info("%s: %s (%.1fs)", name, result.summary(), elapsed)
        if result.errors:
            for err in result.errors[:10]:
                logger.warning("  error: %s", err)

    # Watcher
    if args.no_watch:
        logger.info("Watching disabled. Initial index complete. Exiting.")
        graph.close()
        return

    from cairn.code.watcher import CodeWatcher

    watcher = CodeWatcher(parser, graph)
    for name, path, _ in projects:
        watcher.watch(project=name, project_id=project_ids[name], root=path)
    watcher.start()
    logger.info("Watching for changes. Ctrl+C to stop.")

    # Wait for signal
    stop = False

    def _handle_signal(signum, frame):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    while not stop:
        try:
            time.sleep(1)
        except KeyboardInterrupt:
            break

    logger.info("Shutting down...")
    watcher.stop()
    graph.close()
    logger.info("Cairn code worker stopped.")


if __name__ == "__main__":
    main()
