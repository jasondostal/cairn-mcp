"""Project tools: projects, code_query, arch_check, dispatch."""

import logging

from cairn.api.utils import parse_multi
from cairn.core.services import Services
from cairn.core.trace import set_trace_project, set_trace_tool
from cairn.tools.auth import check_project_access, require_admin
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
        - 'link': Link two projects together.
        - 'get_links': Get all links for a project.

        Args:
            action: One of 'list', 'create_doc', 'get_docs', 'get_doc', 'list_all_docs', 'update_doc', 'link', 'get_links'.
            project: Project name (required for most actions; optional comma-separated filter for list_all_docs).
            doc_type: Document type: 'brief', 'prd', 'plan', 'primer', 'writeup', or 'guide' (for create_doc, optional comma-separated filter for get_docs/list_all_docs).
            content: Document content (required for create_doc, update_doc). Can be omitted if file_path is provided.
            doc_id: Document ID (required for update_doc, get_doc).
            title: Optional document title (for create_doc, update_doc).
            target: Target project name (required for link).
            link_type: Relationship type for link (default 'related').
            file_path: Path to a local file in the server's ingest staging directory.
                Use instead of content to ingest from a staging directory (avoids inline transfer).
            limit: Max results to return (for list_all_docs).
            offset: Pagination offset (for list_all_docs, default 0).
        """
        try:
            set_trace_tool("projects")
            if project:
                set_trace_project(project)
            check_project_access(svc, project)
            if not project and action not in ("list", "get_doc", "list_all_docs"):
                return {"error": "project is required for this action"}

            def _do_projects():
                nonlocal content, title

                # Resolve file_path for create_doc/update_doc
                if file_path and not content and action in ("create_doc", "update_doc"):
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

                if action == "link":
                    if not target:
                        return {"error": "target project is required for link"}
                    return svc.project_manager.link(project, target, link_type)

                if action == "get_links":
                    return svc.project_manager.get_links(project)

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
    async def dispatch(
        work_item_id: int | str | None = None,
        project: str | None = None,
        title: str | None = None,
        description: str | None = None,
        backend: str | None = None,
        risk_tier: int | None = None,
        model: str | None = None,
        agent: str | None = None,
        assignee: str | None = None,
    ) -> dict:
        """Dispatch work to a background agent — tracked, briefed, heartbeating.

        USE THIS instead of native subagents (Task tool) when:
        - The work will take more than a few minutes
        - You want the job tracked (visible in cairn-ui, queryable, resumable)
        - You want to continue working on other things in parallel
        - The task involves a different codebase or working directory
        - You want heartbeat monitoring and gate support

        DO NOT USE when:
        - The task is quick (< 2 minutes) and you need the result immediately
        - You're doing a simple lookup or computation

        Two modes:
        - Dispatch an existing work item: pass work_item_id
        - Create + dispatch in one shot: pass project + title (+ optional description)

        Internally: creates/resolves work item → claims it → generates briefing →
        creates workspace session → sends briefing to agent. One call does it all.

        The dispatched agent gets Cairn MCP access and will heartbeat progress
        back. Check status via work_items(action='get', work_item_id=...).

        Args:
            work_item_id: Existing work item to dispatch (display_id like 'ca-42' or numeric ID).
            project: Project name (required if creating a new work item).
            title: Work item title (required if creating a new work item).
            description: Detailed description of the work to be done.
            backend: Agent backend: 'claude_code' or 'opencode'. Auto-selects if omitted.
            risk_tier: Permission level (0=full autonomy, 1=broad, 2=read-heavy, 3=research-only).
            model: Model override for Claude Code (e.g. 'claude-sonnet-4-6').
            agent: Agent definition to use (defaults to workspace config).
            assignee: Name for the agent claim (auto-generated if omitted).
        """
        try:
            set_trace_tool("dispatch")
            if project:
                set_trace_project(project)
            require_admin(svc)
            check_project_access(svc, project)
            if svc.workspace_manager is None:
                return {"error": "workspace manager not available"}
            return await in_thread(
                svc.db,
                svc.workspace_manager.dispatch,
                work_item_id=work_item_id,
                project=project,
                title=title,
                description=description,
                backend=backend,
                risk_tier=risk_tier,
                model=model,
                agent=agent,
                assignee=assignee,
            )
        except Exception as e:
            logger.exception("dispatch failed")
            return {"error": f"Internal error: {e}"}
