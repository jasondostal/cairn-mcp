"""Insight tools: insights, beliefs, drift_check, decay_scan, think."""

import logging

from cairn.core.budget import apply_list_budget
from cairn.core.constants import BUDGET_INSIGHTS_PER_ITEM
from cairn.core.services import Services
from cairn.core.trace import set_trace_project, set_trace_tool
from cairn.tools.auth import check_project_access, require_admin
from cairn.tools.threading import in_thread

logger = logging.getLogger("cairn")


def register(mcp, svc: Services):
    """Register insight-domain tools on the MCP instance.

    Args:
        mcp: FastMCP server instance.
        svc: Initialized Services dataclass.
    """

    @mcp.tool()
    async def insights(
        project: str | None = None,
        topic: str | None = None,
        min_confidence: float = 0.5,
        limit: int = 10,
    ) -> dict:
        """Discover patterns across stored memories using semantic clustering.

        TRIGGER: When the user wants meta-analysis or pattern discovery:
        - "what patterns", "what trends", "what's recurring", "common themes"
        - "best practices", "what can we learn from", "how has X evolved"
        - "analyze across", "cross-project", "what do these have in common"

        WHEN TO USE: For big-picture analysis, not simple lookups (use search for those).
        Proactively use during complex discussions to surface patterns the user hasn't noticed.

        Uses HDBSCAN to group semantically similar memories into clusters, then
        generates labels and summaries for each cluster. Clustering runs lazily:
        only when stale (>24h, >20% growth, or first run).

        Args:
            project: Filter to a specific project. Omit for cross-project analysis.
            topic: Optional topic to filter clusters by semantic similarity.
            min_confidence: Minimum cluster confidence score (0.0-1.0, default 0.5).
            limit: Maximum clusters to return (default 10).
        """
        try:
            set_trace_tool("insights")
            if project:
                set_trace_project(project)
            check_project_access(svc, project)

            def _do_insights():
                # Check staleness and recluster if needed
                reclustered = False
                labeling_error = None
                if svc.cluster_engine.is_stale(project):
                    cluster_result = svc.cluster_engine.run_clustering(project)
                    reclustered = True
                    labeling_error = cluster_result.get("labeling_error")

                # Fetch clusters
                clusters = svc.cluster_engine.get_clusters(
                    project=project,
                    topic=topic,
                    min_confidence=min_confidence,
                    limit=limit,
                )

                last_run = svc.cluster_engine.get_last_run(project)

                # Apply budget cap to cluster summaries
                budget = svc.config.budget.insights
                overflow_msg = ""
                if budget > 0 and clusters:
                    clusters, meta = apply_list_budget(
                        clusters, budget, "summary",
                        per_item_max=BUDGET_INSIGHTS_PER_ITEM,
                        overflow_message=(
                            "...{omitted} clusters omitted. "
                            "Use a topic filter or increase limit for targeted results."
                        ),
                    )
                    if meta["omitted"] > 0:
                        overflow_msg = meta["overflow_message"]

                result = {
                    "status": "reclustered" if reclustered else "cached",
                    "cluster_count": len(clusters),
                    "clusters": clusters,
                    "last_clustered_at": last_run["created_at"] if last_run else None,
                }
                if labeling_error:
                    result["labeling_warning"] = labeling_error
                if overflow_msg:
                    result["_overflow"] = overflow_msg
                return result

            return await in_thread(svc.db, _do_insights)
        except Exception as e:
            logger.exception("insights failed")
            return {"error": f"Internal error: {e}"}

    @mcp.tool()
    async def beliefs(
        action: str,
        project: str,
        content: str | None = None,
        domain: str | None = None,
        confidence: float = 0.7,
        evidence_ids: list[int] | None = None,
        agent_name: str | None = None,
        belief_id: int | None = None,
        reason: str | None = None,
        confidence_delta: float = -0.1,
    ) -> dict:
        """Manage durable beliefs — post-decisional knowledge with confidence tracking.

        Beliefs are things an agent or the organization holds as true through experience.
        They have confidence scores, domain tags, evidence linking, and can be challenged
        or retracted. Beliefs are the downstream of working memory — hypotheses that
        crystallized, tensions that resolved, observations that solidified.

        Actions:
        - 'crystallize': Create a new belief (project, content). Optional: domain, confidence,
          evidence_ids, agent_name.
        - 'list': List beliefs (project). Optional: agent_name, domain, status.
        - 'get': Get full detail (belief_id).
        - 'challenge': Lower confidence on a belief (belief_id). Optional: evidence_id,
          reason, confidence_delta.
        - 'retract': Mark a belief as wrong (belief_id). Optional: reason.

        Args:
            action: One of 'crystallize', 'list', 'get', 'challenge', 'retract'.
            project: Project name.
            content: Belief content (required for crystallize).
            domain: Area of expertise (deployment, architecture, etc.).
            confidence: Initial confidence 0.0-1.0 (crystallize only).
            evidence_ids: Memory IDs supporting or challenging the belief.
            agent_name: Who holds this belief (None = organizational).
            belief_id: Belief ID (required for get, challenge, retract).
            reason: Explanation for challenge or retraction.
            confidence_delta: How much to adjust confidence on challenge (default -0.1).
        """
        try:
            set_trace_tool("beliefs")
            set_trace_project(project)
            check_project_access(svc, project)
            if not svc.belief_store:
                return {"error": "BeliefStore not initialized"}

            if action == "crystallize":
                if not content:
                    return {"error": "content is required for crystallize"}
                return await in_thread(
                    svc.db,
                    svc.belief_store.crystallize, project, content,
                    domain=domain, confidence=confidence,
                    evidence_ids=evidence_ids, agent_name=agent_name,
                )
            elif action == "list":
                return await in_thread(
                    svc.db,
                    svc.belief_store.list_beliefs, project,
                    agent_name=agent_name, domain=domain,
                )
            elif action == "get":
                if belief_id is None:
                    return {"error": "belief_id is required for get"}
                result = await in_thread(svc.db, svc.belief_store.get, belief_id)
                return result or {"error": f"Belief {belief_id} not found"}
            elif action == "challenge":
                if belief_id is None:
                    return {"error": "belief_id is required for challenge"}
                return await in_thread(
                    svc.db,
                    svc.belief_store.challenge, belief_id,
                    evidence_id=evidence_ids[0] if evidence_ids else None,
                    reason=reason, confidence_delta=confidence_delta,
                )
            elif action == "retract":
                if belief_id is None:
                    return {"error": "belief_id is required for retract"}
                return await in_thread(
                    svc.db,
                    svc.belief_store.retract, belief_id, reason=reason,
                )
            else:
                return {"error": f"Unknown action '{action}'. Use: crystallize, list, get, challenge, retract"}
        except Exception as e:
            logger.exception("beliefs failed")
            return {"error": f"Internal error: {e}"}

    @mcp.tool()
    async def drift_check(
        project: str | None = None,
        files: list[dict] | None = None,
    ) -> dict:
        """Check for memories with stale file references via content hash comparison.

        WHEN TO USE: Verify if stored memories about code/config files are still accurate.
        - Before relying on a stored memory about a specific file's contents
        - Periodic maintenance to find outdated code-snippet or decision memories
        - After major refactors to identify memories that need updating

        Pull-based: the caller computes and provides current file hashes because
        Cairn may run on a different host than the codebase. Returns memories where
        the referenced files have changed since the memory was stored.

        Args:
            project: Filter to a specific project. Omit to check all.
            files: List of {path: str, hash: str} — current file content hashes.
                   Use sha256 or any consistent hash of file contents.
        """
        try:
            set_trace_tool("drift_check")
            if project:
                set_trace_project(project)
            check_project_access(svc, project)
            if svc.drift_detector is None:
                return {"error": "drift detector not available"}
            return await in_thread(svc.db, svc.drift_detector.check, project=project, files=files)
        except Exception as e:
            logger.exception("drift_check failed")
            return {"error": f"Internal error: {e}"}

    @mcp.tool()
    async def decay_scan(
        project: str | None = None,
        dry_run: bool = True,
    ) -> dict:
        """Scan for memories at risk of being forgotten by the decay system.

        WHEN TO USE: Understanding what the decay system would forget.
        - "what memories are decaying", "show me at-risk memories"
        - Verifying decay thresholds before enabling live mode

        Returns candidates with decay scores and protected status.
        Always dry-run by default — never forgets on its own.

        Args:
            project: Optional project filter.
            dry_run: Always True for this tool (inspection only).
        """
        try:
            set_trace_tool("decay_scan")
            require_admin(svc)
            if not svc.decay_worker:
                return {"error": "DecayWorker is not enabled"}
            return await in_thread(svc.db, svc.decay_worker.scan)
        except Exception as e:
            logger.exception("decay_scan failed")
            return {"error": f"Internal error: {e}"}

    @mcp.tool()
    async def think(
        action: str,
        project: str,
        goal: str | None = None,
        sequence_id: int | None = None,
        thought: str | None = None,
        thought_type: str = "general",
        branch_name: str | None = None,
        author: str | None = None,
    ) -> dict | list[dict]:
        """Structured thinking sequences for collaborative reasoning.

        TRIGGER: When a problem has multiple valid approaches or needs step-by-step analysis:
        - "think through", "analyze", "reason about", "let's consider"
        - Architecture decisions with trade-offs
        - Debugging complex issues (hypothesis → test → observe → conclude)
        - Planning multi-step implementations
        - Any problem where the user wants to participate in the reasoning

        This is a COLLABORATIVE tool — both humans and agents contribute thoughts.
        Use author to attribute who contributed each thought. The exploration
        itself becomes searchable knowledge.

        PATTERN: start (with goal) → add thoughts (observations, hypotheses, analysis) → conclude
        Use 'alternative' or 'branch' thought_type to explore divergent paths.
        Use 'reopen' to resume a completed sequence across sessions.

        WHEN NOT TO USE: Simple questions (use search), straightforward tasks, quick lookups.

        Actions:
        - 'start': Begin a new thinking sequence with a goal.
        - 'add': Add a thought to an active sequence.
        - 'conclude': Finalize a sequence with a conclusion.
        - 'reopen': Reopen a completed sequence for continued thinking.
        - 'get': Retrieve a full sequence with all thoughts.
        - 'list': List thinking sequences for a project.
        - 'summarize': Structured deliberation summary — decisions, tradeoffs, risks, dependencies (sequence_id).

        Args:
            action: One of 'start', 'add', 'conclude', 'reopen', 'get', 'list'.
            project: Project name.
            goal: The problem or goal (required for start).
            sequence_id: Sequence ID (required for add, conclude, reopen, get).
            thought: The thought content (required for add, conclude).
            thought_type: Type: observation, hypothesis, question, reasoning, conclusion,
                          assumption, analysis, general, alternative, branch,
                          insight, realization, pattern, challenge, response.
            branch_name: Name for a branch when thought_type is alternative/branch.
            author: Who contributed this thought (e.g., "human", "assistant", a name).
        """
        try:
            set_trace_tool("think")
            set_trace_project(project)
            check_project_access(svc, project)

            def _do_think():
                if action == "start":
                    if not goal:
                        return {"error": "goal is required for start"}
                    return svc.thinking_engine.start(project, goal)

                if action == "add":
                    if not sequence_id or not thought:
                        return {"error": "sequence_id and thought are required for add"}
                    return svc.thinking_engine.add_thought(sequence_id, thought, thought_type, branch_name, author)

                if action == "conclude":
                    if not sequence_id or not thought:
                        return {"error": "sequence_id and thought (conclusion) are required for conclude"}
                    return svc.thinking_engine.conclude(sequence_id, thought, author)

                if action == "reopen":
                    if not sequence_id:
                        return {"error": "sequence_id is required for reopen"}
                    return svc.thinking_engine.reopen(sequence_id)

                if action == "get":
                    if not sequence_id:
                        return {"error": "sequence_id is required for get"}
                    return svc.thinking_engine.get_sequence(sequence_id)

                if action == "list":
                    return svc.thinking_engine.list_sequences(project)["items"]

                if action == "summarize":
                    if not sequence_id:
                        return {"error": "sequence_id is required for summarize"}
                    return svc.thinking_engine.summarize_deliberation(sequence_id)

                return {"error": f"Unknown action: {action}"}

            return await in_thread(svc.db, _do_think)
        except Exception as e:
            logger.exception("think failed")
            return {"error": f"Internal error: {e}"}
