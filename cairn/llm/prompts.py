"""LLM prompt templates for all Cairn capabilities."""

from cairn.core.constants import VALID_MEMORY_TYPES  # noqa: F401 — re-exported for backwards compat

ENRICHMENT_SYSTEM_PROMPT = """\
You are a memory classification system. Analyze the provided content and return a JSON object with exactly these fields:

{
  "tags": ["tag1", "tag2", ...],
  "importance": 0.7,
  "memory_type": "decision",
  "summary": "One-sentence summary."
}

Rules:
- tags: 3-7 lowercase, hyphenated keywords that categorize this content. Focus on topics, technologies, and concepts.
- importance: Float 0.0-1.0. Use this scale:
  - 0.9-1.0: Critical decisions, architectural choices, production incidents
  - 0.7-0.8: Important learnings, key implementation details, significant bugs
  - 0.5-0.6: Normal working notes, routine progress updates
  - 0.3-0.4: Minor observations, tangential notes
- memory_type: One of: note, decision, rule, code-snippet, learning, research, discussion, progress, task, debug, design
- summary: A single concise sentence for progressive disclosure. Should let a reader decide whether to read the full content.

Return ONLY the JSON object. No markdown fences, no explanation, no extra text."""


def build_enrichment_messages(content: str) -> list[dict]:
    """Build the message list for a single enrichment LLM call."""
    return [
        {"role": "system", "content": ENRICHMENT_SYSTEM_PROMPT},
        {"role": "user", "content": content},
    ]


# ============================================================
# Cluster Summary Prompt (Phase 3)
# ============================================================

CLUSTER_SUMMARY_SYSTEM_PROMPT = """\
You are a pattern discovery system. You are given groups of memory summaries and tags \
that have been clustered by semantic similarity. For each cluster, produce a short label \
and a one-sentence summary that captures the common theme.

Return a JSON array of objects with exactly these fields:

[
  {"cluster_id": 0, "label": "Short Label", "summary": "One-sentence description of common theme."},
  ...
]

Rules:
- label: 2-5 words, title case. Describes the cluster's topic (e.g., "Docker Configuration", "Auth Flow Decisions").
- summary: One sentence describing what the memories in this cluster have in common.
- cluster_id: Must match the cluster_id provided in the input.
- Return ONLY the JSON array. No markdown fences, no explanation, no extra text."""


def build_cluster_summary_messages(clusters: dict[int, list[str]]) -> list[dict]:
    """Build messages for cluster summary LLM call.

    Args:
        clusters: Mapping of cluster_id -> list of "summary [tags]" strings.
    """
    lines = []
    for cluster_id, members in clusters.items():
        lines.append(f"--- Cluster {cluster_id} ({len(members)} memories) ---")
        for member in members:
            lines.append(f"  - {member}")
    user_content = "\n".join(lines)

    return [
        {"role": "system", "content": CLUSTER_SUMMARY_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


# ============================================================
# Query Expansion Prompt (v0.6.0)
# ============================================================

QUERY_EXPANSION_SYSTEM_PROMPT = """\
You are a search query expansion system. Given a short search query, expand it with \
related terms, synonyms, and contextual keywords that would help find relevant results \
in a semantic memory system.

Rules:
- Return ONLY the expanded query as plain text (no JSON, no markdown, no explanation).
- Keep the original query terms and add 3-8 related terms.
- Focus on synonyms, related concepts, and technical terms.
- Keep it to a single line, space-separated."""


def build_query_expansion_messages(query: str) -> list[dict]:
    """Build messages for query expansion LLM call."""
    return [
        {"role": "system", "content": QUERY_EXPANSION_SYSTEM_PROMPT},
        {"role": "user", "content": query},
    ]


# ============================================================
# Relationship Extraction Prompt (v0.6.0)
# ============================================================

RELATIONSHIP_EXTRACTION_SYSTEM_PROMPT = """\
You are a relationship detection system. You are given a new memory and a list of \
candidate memories that are semantically similar. Determine which candidates are \
genuinely related to the new memory and how.

Return a JSON array of objects. Each object represents a confirmed relationship:

[
  {"id": 42, "relation": "extends"},
  {"id": 17, "relation": "related"}
]

Valid relation types: extends, contradicts, implements, depends_on, related.

Rules:
- Only include genuinely related memories. If none are related, return an empty array [].
- "extends" = the new memory builds on or adds detail to the candidate.
- "contradicts" = the new memory conflicts with or supersedes the candidate.
- "implements" = the new memory is a concrete implementation of the candidate.
- "depends_on" = the new memory requires or references the candidate.
- "related" = general topical relationship.
- Return ONLY the JSON array. No markdown fences, no explanation."""


def build_relationship_extraction_messages(
    new_content: str, candidates: list[dict],
) -> list[dict]:
    """Build messages for relationship extraction.

    Args:
        new_content: The content of the newly stored memory.
        candidates: List of dicts with 'id', 'content'/'summary' of neighbor memories.
    """
    candidate_lines = []
    for c in candidates:
        text = c.get("summary") or c.get("content", "")[:300]
        candidate_lines.append(f"  ID {c['id']}: {text}")

    user_content = (
        f"New memory:\n{new_content}\n\n"
        f"Candidate memories:\n" + "\n".join(candidate_lines)
    )
    return [
        {"role": "system", "content": RELATIONSHIP_EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


# ============================================================
# Rule Conflict Detection Prompt (v0.6.0)
# ============================================================

RULE_CONFLICT_SYSTEM_PROMPT = """\
You are a rule conflict detection system. You are given a new rule and a list of \
existing rules. Identify any conflicts or contradictions between the new rule and \
existing rules.

Return a JSON array of conflict objects:

[
  {"rule_id": 5, "conflict": "Brief description of the conflict", "severity": "high"}
]

Severity levels: high (direct contradiction), medium (partial conflict), low (potential tension).

Rules:
- Only report genuine conflicts. If there are no conflicts, return an empty array [].
- Be precise about what conflicts. Complementary rules are not conflicts.
- Return ONLY the JSON array. No markdown fences, no explanation."""


def build_rule_conflict_messages(
    new_rule: str, existing_rules: list[dict],
) -> list[dict]:
    """Build messages for rule conflict detection.

    Args:
        new_rule: Content of the new rule being stored.
        existing_rules: List of dicts with 'id', 'content' of existing rules.
    """
    rule_lines = []
    for r in existing_rules:
        rule_lines.append(f"  Rule #{r['id']}: {r['content']}")

    user_content = (
        f"New rule:\n{new_rule}\n\n"
        f"Existing rules:\n" + "\n".join(rule_lines)
    )
    return [
        {"role": "system", "content": RULE_CONFLICT_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


# ============================================================
# Session Synthesis Prompt (v0.6.0)
# ============================================================

SESSION_SYNTHESIS_SYSTEM_PROMPT = """\
You are a session narrative synthesizer. You are given a chronological list of memories \
from a working session. Synthesize them into a coherent narrative of 2-4 paragraphs that \
captures what happened during the session, key decisions made, problems encountered, and \
outcomes achieved.

Rules:
- Write in past tense, third person.
- Focus on the arc of work: what was attempted, what was learned, what was decided.
- Highlight key decisions, blockers, and breakthroughs.
- Return ONLY the narrative text. No JSON, no markdown headers, no extra formatting."""


def build_session_synthesis_messages(
    memories: list[dict], project: str, session_name: str,
) -> list[dict]:
    """Build messages for session synthesis.

    Args:
        memories: Chronological list of memory dicts with 'content', 'summary', etc.
        project: Project name for context.
        session_name: Session identifier.
    """
    memory_lines = []
    for m in memories:
        text = m.get("summary") or m.get("content", "")[:300]
        mtype = m.get("memory_type", "note")
        memory_lines.append(f"  [{mtype}] {text}")

    user_content = (
        f"Project: {project}\n"
        f"Session: {session_name}\n\n"
        f"Memories (chronological):\n" + "\n".join(memory_lines)
    )
    return [
        {"role": "system", "content": SESSION_SYNTHESIS_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


# ============================================================
# Consolidation Prompt (v0.6.0)
# ============================================================

CONSOLIDATION_SYSTEM_PROMPT = """\
You are a memory consolidation advisor. You are given pairs of highly similar memories \
from a project. For each pair, recommend an action.

Return a JSON array of recommendation objects:

[
  {"action": "merge", "inactivate_id": 42, "keep_id": 17, "reason": "Duplicate content"},
  {"action": "promote", "memory_id": 42, "reason": "Pattern observed across multiple notes"},
  {"action": "inactivate", "memory_id": 42, "reason": "Superseded by newer memory"}
]

Valid actions:
- "merge": One memory subsumes the other. Specify which to keep and which to inactivate.
- "promote": A note/learning should be promoted to a rule.
- "inactivate": Memory is outdated or redundant.

Rules:
- Only recommend actions with clear justification.
- If a pair looks similar but both are valuable, skip it.
- Return ONLY the JSON array. No markdown fences, no explanation."""


def build_consolidation_messages(
    candidates: list[dict], project: str,
) -> list[dict]:
    """Build messages for consolidation.

    Args:
        candidates: List of similar-pair dicts with id_a, id_b, similarity, summary_a, summary_b.
        project: Project name for context.
    """
    pair_lines = []
    for c in candidates:
        pair_lines.append(
            f"  Pair (similarity={c['similarity']}):\n"
            f"    Memory #{c['id_a']}: {c['summary_a']}\n"
            f"    Memory #{c['id_b']}: {c['summary_b']}"
        )

    user_content = (
        f"Project: {project}\n\n"
        f"Similar memory pairs:\n" + "\n".join(pair_lines)
    )
    return [
        {"role": "system", "content": CONSOLIDATION_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


# ============================================================
# Confidence Gating Prompt (v0.6.0)
# ============================================================

CONFIDENCE_GATING_SYSTEM_PROMPT = """\
You are a search result quality assessor. You are given a search query and a list of \
results. Assess whether the results actually answer the query.

Return a JSON object:

{
  "confidence": 0.8,
  "assessment": "Brief explanation of result quality",
  "best_match_id": 42,
  "irrelevant_ids": [5, 7]
}

Rules:
- confidence: 0.0-1.0. How well do the results answer the query?
  - 0.9-1.0: Results directly and completely answer the query.
  - 0.7-0.8: Results are mostly relevant with good coverage.
  - 0.4-0.6: Results are partially relevant or tangential.
  - 0.0-0.3: Results don't meaningfully address the query.
- best_match_id: ID of the single most relevant result (or null if none are relevant).
- irrelevant_ids: IDs of results that don't belong in the result set.
- Return ONLY the JSON object. No markdown fences, no explanation."""


# ============================================================
# Cairn Narrative Prompt (v0.7.0 — Episodic Memory)
# ============================================================

CAIRN_NARRATIVE_SYSTEM_PROMPT = """\
You are a session narrative synthesizer. You are given a chronological list of memories \
(stones) from a working session. Produce a JSON object with a title and narrative.

Return a JSON object:

{
  "title": "Short session title (5-10 words)",
  "narrative": "2-4 paragraph narrative of the session."
}

Rules for the title:
- 5-10 words, descriptive of the session's main arc.
- Focus on what was accomplished or decided, not process.

Rules for the narrative:
- Write in past tense, third person.
- Focus on the arc of work: what was attempted, what was learned, what was decided.
- Highlight key decisions, blockers, and breakthroughs.
- 2-4 paragraphs.

Return ONLY the JSON object. No markdown fences, no explanation, no extra text."""

CAIRN_MOTE_NARRATIVE_SYSTEM_PROMPT = """\
You are a session narrative synthesizer. You are given two sources of information about a \
working session:

1. **Stones** — explicitly stored memories (decisions, learnings, notes). May be empty.
2. **Motes** — a timeline of tool calls and events captured by hooks during the session.

Synthesize both sources into a coherent narrative. The motes reveal what actually happened \
(files read, edits made, commands run); the stones capture what the agent considered important \
enough to remember. Together they tell the full story.

Return a JSON object:

{
  "title": "Short session title (5-10 words)",
  "narrative": "2-4 paragraph narrative of the session."
}

Rules for the title:
- 5-10 words, descriptive of the session's main arc.
- Focus on what was accomplished or decided, not process.

Rules for the narrative:
- Write in past tense, third person.
- Weave the mote timeline and stone insights into a single coherent arc.
- Focus on what was attempted, what was learned, what was decided.
- Highlight key decisions, blockers, and breakthroughs.
- 2-4 paragraphs.

Return ONLY the JSON object. No markdown fences, no explanation, no extra text."""


def build_cairn_narrative_messages(
    memories: list[dict], project: str, session_name: str,
    events: list[dict] | None = None,
) -> list[dict]:
    """Build messages for cairn narrative synthesis.

    Args:
        memories: Chronological list of memory dicts (stones) with 'content', 'summary', etc.
        project: Project name for context.
        session_name: Session identifier.
        events: Optional list of mote events from hooks. When present, the mote-aware
                prompt is used and the event timeline is appended to the user content.
    """
    memory_lines = []
    for m in memories:
        text = m.get("summary") or m.get("content", "")[:300]
        mtype = m.get("memory_type", "note")
        memory_lines.append(f"  [{mtype}] {text}")

    user_content = (
        f"Project: {project}\n"
        f"Session: {session_name}\n"
        f"Stone count: {len(memories)}\n\n"
        f"Stones (chronological):\n" + ("\n".join(memory_lines) if memory_lines else "  (none)")
    )

    # Choose prompt based on whether events are available
    if events:
        # Limit to last 50 events to avoid context overflow
        trimmed = events[-50:] if len(events) > 50 else events
        event_lines = []
        for e in trimmed:
            ts = e.get("ts", "")
            etype = e.get("type", "unknown")
            # Build a concise one-liner per event
            detail = _summarize_event(e)
            event_lines.append(f"  [{ts}] {etype}: {detail}")

        user_content += (
            f"\n\nMote timeline ({len(events)} events"
            + (f", showing last 50" if len(events) > 50 else "")
            + f"):\n" + "\n".join(event_lines)
        )
        system_prompt = CAIRN_MOTE_NARRATIVE_SYSTEM_PROMPT
    else:
        system_prompt = CAIRN_NARRATIVE_SYSTEM_PROMPT

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]


def _summarize_event(event: dict) -> str:
    """Produce a concise one-liner for a mote event."""
    etype = event.get("type", "")
    if etype == "tool_call":
        tool = event.get("tool", "unknown")
        # Include key detail fields if present
        path = event.get("path") or event.get("file_path") or ""
        return f"{tool}" + (f" {path}" if path else "")
    if etype in ("session_start", "session_end"):
        return event.get("project", event.get("reason", ""))
    # Generic: show all keys except ts/type
    extras = {k: v for k, v in event.items() if k not in ("ts", "type")}
    if extras:
        parts = [f"{k}={v}" for k, v in list(extras.items())[:3]]
        return ", ".join(parts)
    return ""


# ============================================================
# Event Digest Prompt (v0.12.0 — Pipeline v2)
# ============================================================

EVENT_DIGEST_SYSTEM_PROMPT = """\
You are writing a work log entry for a colleague picking up this work tomorrow. \
You are given a batch of tool interactions from an AI coding session.

Focus on:
- What TOPICS were worked on (not what tools were called)
- What was DISCOVERED (important findings, state of the system)
- What CHANGED (files edited, configs deployed, services restarted)
- What FAILED or was abandoned (dead-end investigations)

Rules:
- Write 2-4 sentences in past tense.
- Be specific: mention file names, service names, error messages when relevant.
- Do NOT list tool names or count tool calls. Describe the work, not the tooling.
- Return ONLY the work log text. No JSON, no markdown, no headers."""


def build_event_digest_messages(
    events: list[dict], project: str, session_name: str, batch_number: int,
) -> list[dict]:
    """Build messages for event batch digest.

    Args:
        events: List of raw event dicts from a single batch.
        project: Project name for context.
        session_name: Session identifier.
        batch_number: Which batch this is (for ordering context).
    """
    event_lines = []
    for e in events:
        ts = e.get("ts", "")
        tool = e.get("tool_name", e.get("tool", ""))
        # Show tool_input keys for context
        tool_input = e.get("tool_input", {})
        if isinstance(tool_input, dict):
            input_hint = ", ".join(f"{k}={str(v)[:80]}" for k, v in list(tool_input.items())[:5])
        else:
            input_hint = str(tool_input)[:200]
        # Show tool_response hint (first 200 chars)
        response = e.get("tool_response", "")
        response_hint = str(response)[:200] if response else ""

        line = f"  [{ts}] {tool}"
        if input_hint:
            line += f" | {input_hint}"
        if response_hint:
            line += f" → {response_hint}"
        event_lines.append(line)

    user_content = (
        f"Project: {project}\n"
        f"Session: {session_name}\n"
        f"Batch: {batch_number}\n"
        f"Event count: {len(events)}\n\n"
        f"Tool interactions:\n" + "\n".join(event_lines)
    )

    return [
        {"role": "system", "content": EVENT_DIGEST_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


# ============================================================
# Cairn Digest Narrative Prompt (v0.12.0 — Pipeline v2)
# ============================================================

CAIRN_DIGEST_NARRATIVE_SYSTEM_PROMPT = """\
You are a session narrative synthesizer. You are given two sources of information about a \
working session:

1. **Stones** — explicitly stored memories (decisions, learnings, notes). May be empty.
2. **Digests** — pre-summarized work log entries from incremental event processing. Each \
digest covers a batch of tool interactions and captures what was worked on, discovered, \
changed, or abandoned.

Synthesize both sources into a coherent narrative. The digests reveal the arc of work \
(what was explored, what changed, what broke); the stones capture what the agent considered \
important enough to remember explicitly.

Return a JSON object:

{
  "title": "Short session title (5-10 words)",
  "narrative": "2-4 paragraph narrative of the session."
}

Rules for the title:
- 5-10 words, descriptive of the session's main arc.
- Focus on what was accomplished or decided, not process.

Rules for the narrative:
- Write in past tense, third person.
- Weave the digests and stone insights into a single coherent arc.
- Focus on what was attempted, what was learned, what was decided.
- Highlight key decisions, blockers, and breakthroughs.
- 2-4 paragraphs.

Return ONLY the JSON object. No markdown fences, no explanation, no extra text."""


def build_cairn_digest_narrative_messages(
    memories: list[dict], project: str, session_name: str,
    digests: list[dict],
) -> list[dict]:
    """Build messages for cairn narrative synthesis from pre-digested event batches.

    Args:
        memories: Chronological list of memory dicts (stones).
        project: Project name for context.
        session_name: Session identifier.
        digests: List of dicts with 'batch_number' and 'digest' text from session_events.
    """
    memory_lines = []
    for m in memories:
        text = m.get("summary") or m.get("content", "")[:300]
        mtype = m.get("memory_type", "note")
        memory_lines.append(f"  [{mtype}] {text}")

    digest_lines = []
    for d in digests:
        batch = d.get("batch_number", "?")
        text = d.get("digest", "(no digest)")
        digest_lines.append(f"  [Batch {batch}] {text}")

    user_content = (
        f"Project: {project}\n"
        f"Session: {session_name}\n"
        f"Stone count: {len(memories)}\n"
        f"Digest count: {len(digests)}\n\n"
        f"Stones (chronological):\n" + ("\n".join(memory_lines) if memory_lines else "  (none)")
        + f"\n\nWork log digests (chronological):\n" + ("\n".join(digest_lines) if digest_lines else "  (none)")
    )

    return [
        {"role": "system", "content": CAIRN_DIGEST_NARRATIVE_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


# ============================================================
# Content Classification Prompt (v0.16.0 — Smart Ingestion)
# ============================================================

CLASSIFICATION_SYSTEM_PROMPT = """\
You classify content for a knowledge management system. Determine how to store the given content.

Return a JSON object with exactly one field:
{"type": "doc" | "memory" | "both"}

Guidelines:
- "doc": Long-lived reference material — guides, primers, PRDs, architecture docs, methodology.
  Store whole, not chunked. These are artifacts you'd put on a bookshelf.
- "memory": Working knowledge — decisions, learnings, progress notes, debug logs, session notes.
  Store as memories (chunked if large). These are thoughts, not documents.
- "both": Reference material that should ALSO be searchable at the chunk level.
  Store whole as doc AND chunk into searchable memories.

Return ONLY the JSON object."""


def build_classification_messages(content: str) -> list[dict]:
    """Build messages for content classification LLM call."""
    return [
        {"role": "system", "content": CLASSIFICATION_SYSTEM_PROMPT},
        {"role": "user", "content": content},
    ]


def build_confidence_gating_messages(
    query: str, results: list[dict],
) -> list[dict]:
    """Build messages for confidence gating.

    Args:
        query: The original search query.
        results: List of search result dicts with 'id', 'summary', 'score'.
    """
    result_lines = []
    for r in results:
        summary = r.get("summary", "")
        result_lines.append(f"  ID {r['id']} (score={r.get('score', 0):.4f}): {summary}")

    user_content = (
        f"Query: {query}\n\n"
        f"Results:\n" + "\n".join(result_lines)
    )
    return [
        {"role": "system", "content": CONFIDENCE_GATING_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
