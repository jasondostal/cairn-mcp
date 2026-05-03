"""Project & session tools: projects, code_query, arch_check, orient, rules, status."""

import logging

from cairn.api.utils import parse_multi
from cairn.core.budget import apply_list_budget
from cairn.core.constants import BUDGET_RULES_PER_ITEM
from cairn.core.services import Services
from cairn.core.status import get_status
from cairn.core.trace import set_trace_project, set_trace_tool
from cairn.tools.auth import check_project_access
from cairn.tools.threading import in_thread

logger = logging.getLogger("cairn")


def register(mcp, svc: Services):
    """Register project-domain tools on the MCP instance.

    Args:
        mcp: FastMCP server instance.
        svc: Initialized Services dataclass.
    """

    @mcp.tool()
    async def projects(
        action: str,
        project: str | None = None,
        doc_type: str | None = None,
        content: str | None = None,
        doc_id: int | None = None,
        title: str | None = None,
        target: str | None = None,
        link_type: str = "related",
        file_path: str | None = None,
        separator: str = "\n\n",
        limit: int | None = None,
        offset: int = 0,
    ) -> dict | list[dict]:
        """Manage project documents and relationships. For formal project docs, NOT working notes.

        WHEN TO USE:
        - Creating or updating project briefs, PRDs, plans, primers, writeups, guides
        - Linking related projects together
        - Listing all projects for orientation
        - User asks "what projects do we have", "show me the brief for X"

        DON'T USE FOR: Working notes, progress updates, decisions, learnings — use store() for those.

        Actions:
        - 'list': List all projects with memory counts.
        - 'create_doc': Create a project document (brief, PRD, plan, primer, writeup, or guide).
        - 'get_docs': Get documents for a project, optionally filtered by type.
        - 'get_doc': Get a single document by ID.
        - 'list_all_docs': List documents across all projects with optional filters and pagination.
        - 'update_doc': Update an existing document's content.
        - 'append_doc': Append content to an existing document. Perfect for building
            large docs incrementally — create a skeleton, then append sections one at a time.
            Each append avoids LLM output limits. Optional separator (default: two newlines).
        - 'link': Link two projects together.
        - 'get_links': Get all links for a project.
        - 'attach_file': Upload a file as an attachment to a document.
            Two modes: file_path (server-local) or content (base64) + title (filename).
            Returns the cairn:// URL to embed in markdown content.
        - 'list_attachments': List attachments for a document.

        Args:
            action: One of 'list', 'create_doc', 'get_docs', 'get_doc', 'list_all_docs', 'update_doc', 'append_doc', 'link', 'get_links', 'attach_file', 'list_attachments'.
            project: Project name (required for most actions; optional comma-separated filter for list_all_docs).
            doc_type: Document type: 'brief', 'prd', 'plan', 'primer', 'writeup', or 'guide' (for create_doc, optional comma-separated filter for get_docs/list_all_docs).
            content: Document content (required for create_doc, update_doc). Can be omitted if file_path is provided.
            doc_id: Document ID (required for update_doc, get_doc, attach_file, list_attachments).
            title: Optional document title (for create_doc, update_doc).
            target: Target project name (required for link).
            link_type: Relationship type for link (default 'related').
            file_path: Path to a local file in the server's ingest staging directory.
                Use instead of content to ingest from a staging directory (avoids inline transfer).
                For attach_file: absolute path to the image file on the server's filesystem.
            separator: Separator between existing and appended content (for append_doc, default: two newlines).
            limit: Max results to return (for list_all_docs).
            offset: Pagination offset (for list_all_docs, default 0).
        """
        try:
            set_trace_tool("projects")
            if project:
                set_trace_project(project)
            check_project_access(svc, project)
            if not project and action not in ("list", "get_doc", "list_all_docs", "attach_file", "list_attachments"):
                return {"error": "project is required for this action"}

            def _do_projects():
                nonlocal content, title

                # Resolve file_path for create_doc/update_doc/append_doc
                if file_path and not content and action in ("create_doc", "update_doc", "append_doc"):
                    file_content, inferred_title = svc.ingest_pipeline.read_local_file(file_path)
                    content = file_content
                    if not title:
                        title = inferred_title

                if action == "list":
                    return svc.project_manager.list_all()["items"]

                if action == "create_doc":
                    if not doc_type or not content:
                        return {"error": "doc_type and content are required for create_doc"}
                    return svc.project_manager.create_doc(project, doc_type, content, title=title)

                if action == "get_docs":
                    return svc.project_manager.get_docs(project, doc_type=doc_type)

                if action == "get_doc":
                    if not doc_id:
                        return {"error": "doc_id is required for get_doc"}
                    result = svc.project_manager.get_doc(doc_id)
                    return result if result is not None else {"error": "Document not found"}

                if action == "list_all_docs":
                    return svc.project_manager.list_all_docs(
                        project=parse_multi(project),
                        doc_type=parse_multi(doc_type),
                        limit=limit,
                        offset=offset,
                    )

                if action == "update_doc":
                    if not doc_id or not content:
                        return {"error": "doc_id and content are required for update_doc"}
                    return svc.project_manager.update_doc(doc_id, content, title=title)

                if action == "append_doc":
                    if not doc_id or not content:
                        return {"error": "doc_id and content are required for append_doc"}
                    return svc.project_manager.append_to_doc(doc_id, content, separator=separator)

                if action == "link":
                    if not target:
                        return {"error": "target project is required for link"}
                    return svc.project_manager.link(project, target, link_type)

                if action == "get_links":
                    return svc.project_manager.get_links(project)

                if action == "attach_file":
                    if not doc_id:
                        return {"error": "doc_id is required for attach_file"}
                    import base64
                    import mimetypes
                    import os

                    if content and title:
                        # Base64 mode: content=base64 data, title=filename
                        try:
                            raw = base64.b64decode(content)
                        except Exception:
                            return {"error": "content must be valid base64 when used for attach_file"}
                        att_filename = title
                        mime_type = mimetypes.guess_type(att_filename)[0] or "application/octet-stream"
                        return svc.project_manager.upload_attachment(doc_id, att_filename, mime_type, raw)

                    if file_path:
                        abs_path = os.path.expanduser(file_path)
                        if not os.path.isfile(abs_path):
                            return {"error": f"File not found: {abs_path}"}
                        att_filename = os.path.basename(abs_path)
                        mime_type = mimetypes.guess_type(abs_path)[0] or "application/octet-stream"
                        with open(abs_path, "rb") as f:
                            raw = f.read()
                        return svc.project_manager.upload_attachment(doc_id, att_filename, mime_type, raw)

                    return {"error": "attach_file requires either file_path (server-local) or content (base64) + title (filename)"}

                if action == "list_attachments":
                    if not doc_id:
                        return {"error": "doc_id is required for list_attachments"}
                    return svc.project_manager.list_attachments(doc_id)

                return {"error": f"Unknown action: {action}"}

            return await in_thread(svc.db, _do_projects)
        except ValueError as e:
            return {"error": str(e)}
        except Exception as e:
            logger.exception("projects failed")
            return {"error": f"Internal error: {e}"}

    @mcp.tool()
    async def code_query(
        action: str,
        project: str,
        target: str = "",
        query: str = "",
        kind: str = "",
        depth: int = 3,
        limit: int = 20,
    ) -> dict:
        """Query the code graph for structural information about an indexed project.

        Answers questions like "What depends on this file?", "What's the blast
        radius if I change this module?", and "What symbols are defined here?"

        Requires the code worker (``python -m cairn.code``) to have indexed the project.

        WHEN TO USE:
        - Understanding dependencies before making changes
        - Estimating impact/blast radius of a refactor
        - Exploring the structure of a file or module
        - Finding symbols by name across a project
        - Tracing call chains for security analysis or debugging
        - Finding dead code or high-complexity functions
        - Finding structurally important files (hotspots)
        - Discovering entity-code relationships

        Actions:
        - ``dependents``: Files that import the target. "Who depends on me?"
        - ``dependencies``: Files the target imports. "What do I depend on?"
        - ``structure``: Symbols in the target file, hierarchically organized.
        - ``impact``: Transitive dependents — full blast radius up to *depth* hops.
        - ``search``: Fulltext search over symbol names, signatures, and docstrings.
        - ``hotspots``: Top files by PageRank structural importance.
        - ``callers``: Functions/methods that CALL the target symbol. "Who calls me?"
        - ``callees``: Functions/methods that the target symbol CALLS. "What do I call?"
        - ``call_chain``: Find call chains from *target* to *query* symbol (up to *depth* hops).
        - ``dead_code``: Functions/methods with zero incoming calls.
        - ``complexity``: Symbols ranked by cyclomatic complexity (highest first).
        - ``entities``: Knowledge entities linked to a code file.
        - ``code_for_entity``: Code files/symbols linked to a knowledge entity.
        - ``cross_search``: Search symbols across all indexed projects.
        - ``shared_deps``: Files that appear in multiple indexed projects.
        - ``bridge``: Create REFERENCED_IN edges between knowledge entities and code.

        Args:
            action: One of the actions listed above.
            project: Project name (must be indexed).
            target: File path or qualified symbol name (required for some actions).
            query: Search term (required for search/cross_search).
            kind: Filter symbols by kind: function, method, class, etc. (search only).
            depth: Max traversal depth for impact (default 3).
            limit: Max results (default 20).
        """
        from cairn.core.code_ops import run_code_query

        try:
            set_trace_tool("code_query")
            set_trace_project(project)
            check_project_access(svc, project)
            return await in_thread(
                svc.db,
                run_code_query,
                action=action, project=project, target=target, query=query,
                kind=kind, depth=depth, limit=limit,
                graph_provider=svc.graph_provider, db=svc.db, config=svc.config,
                embedding_engine=svc.embedding,
            )
        except Exception as e:
            logger.exception("code_query failed")
            return {"error": f"Internal error: {e}"}

    @mcp.tool()
    async def arch_check(
        project: str,
        path: str = "",
        config_path: str = "",
        use_graph: bool = False,
    ) -> dict:
        """Check architecture boundary rules and integration contracts.

        Loads rules from a YAML file, a project doc (doc_type='architecture'),
        or the Neo4j code graph. Reports boundary violations and contract breaches.

        Rule sources (checked in order):
        1. ``config_path`` — explicit path to a YAML file
        2. Project doc — architecture doc stored via ``projects(action='create_doc', doc_type='architecture')``
        3. Error if neither is available

        Evaluation modes:
        - **Source** (default): re-parses Python files under ``path`` using stdlib ast.
          Supports both boundary rules and integration contracts.
        - **Graph** (``use_graph=True``): queries Neo4j IMPORTS edges. Faster for
          large codebases, but only evaluates boundary rules (contracts need
          name-level import info unavailable in file-level graph edges).

        WHEN TO USE:
        - Verify architecture boundaries before or after refactoring
        - CI-style checks on a project's codebase
        - Validate that modules only import declared public APIs (contracts)

        Args:
            project: Project name (for loading project-doc rules and graph queries).
            path: Source root directory (required for source-based evaluation).
            config_path: Explicit path to architecture YAML (overrides project doc).
            use_graph: Use Neo4j IMPORTS edges instead of re-parsing source (default: False).
        """
        from cairn.core.code_ops import run_arch_check

        try:
            set_trace_tool("arch_check")
            set_trace_project(project)
            check_project_access(svc, project)
            return await in_thread(
                svc.db,
                run_arch_check,
                project=project, path=path, config_path=config_path,
                use_graph=use_graph,
                graph_provider=svc.graph_provider, db=svc.db, config=svc.config,
                project_manager=svc.project_manager,
            )
        except Exception as e:
            logger.exception("arch_check failed")
            return {"error": f"Internal error: {e}"}

    @mcp.tool()
    async def orient(project: str | None = None) -> dict:
        """Single-pass session boot. Returns rules, trail, learnings, and work items.

        Replaces calling rules() + search() + work_items() individually with one call.
        Each section gets a token budget allocation with surplus flowing to the next.

        Use this at session start. Individual tools remain available for granular
        use mid-session.

        Args:
            project: Project name for scoped rules and work items. Omit for global-only boot.
        """
        from cairn.core.orient import run_orient

        try:
            set_trace_tool("orient")
            if project:
                set_trace_project(project)
            check_project_access(svc, project)

            def _do_orient():
                return run_orient(
                    project=project,
                    config=svc.config,
                    db=svc.db,
                    memory_store=svc.memory_store,
                    search_engine=svc.search_engine,
                    work_item_manager=svc.work_item_manager,
                    graph_provider=svc.graph_provider,
                    belief_store=svc.belief_store,
                )

            return await in_thread(svc.db, _do_orient)
        except Exception as e:
            logger.exception("orient failed")
            return {"error": f"Internal error: {e}"}

    @mcp.tool()
    async def rules(project: str | None = None) -> list[dict]:
        """Get behavioral rules and guardrails.

        CRITICAL: Call this at session start. Rules define how you should behave —
        deployment patterns, communication style, project conventions, safety guardrails.

        Returns rule-type memories from __global__ (universal guardrails) and
        the specified project.

        Args:
            project: Project name to get rules for. Omit for global rules only.
        """
        try:
            set_trace_tool("rules")
            if project:
                set_trace_project(project)
            check_project_access(svc, project)

            def _do_rules():
                result = svc.memory_store.get_rules(project)
                items = result["items"]
                budget = svc.config.budget.rules
                if budget > 0 and items:
                    items, meta = apply_list_budget(
                        items, budget, "content",
                        per_item_max=BUDGET_RULES_PER_ITEM,
                        overflow_message=(
                            "...{omitted} more rules omitted. "
                            "Use search(query='topic', memory_type='rule') for targeted retrieval."
                        ),
                    )
                    if meta["omitted"] > 0:
                        items.append({"_overflow": meta["overflow_message"]})
                return items

            return await in_thread(svc.db, _do_rules)
        except Exception as e:
            logger.exception("rules failed")
            return [{"error": f"Internal error: {e}"}]

    @mcp.tool()
    async def status() -> dict:
        """System health and statistics.

        Quick diagnostic tool — no parameters required.
        Returns version, memory counts, embedding/LLM health, event bus stats.
        """
        try:
            set_trace_tool("status")
            return await in_thread(svc.db, get_status, svc.db, svc.config)
        except Exception as e:
            logger.exception("status failed")
            return {"error": f"Internal error: {e}"}

