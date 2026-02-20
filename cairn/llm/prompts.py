"""LLM prompt templates for all Cairn capabilities."""

from cairn.core.constants import VALID_MEMORY_TYPES  # noqa: F401 — re-exported for backwards compat

ENRICHMENT_SYSTEM_PROMPT = """\
You are a memory classification system. Analyze the provided content and return a JSON object with exactly these fields:

{
  "tags": ["tag1", "tag2", ...],
  "importance": 0.7,
  "memory_type": "decision",
  "summary": "One-sentence summary.",
  "entities": ["Person Name", "Project Name", "Organization"]
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
- entities: 0-15 named entities mentioned in the content. Extract people, places, organizations, projects, products, and technologies. Preserve original casing. Only extract entities explicitly mentioned — do not infer.

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
# Session Synthesis Prompt (v0.41.0 — digest-based synthesis)
# ============================================================

SESSION_SYNTHESIS_SYSTEM_PROMPT = """\
You are a session intelligence extractor. You are given chronological work log entries \
(batch digests) from an AI coding session. Your job is to sift the signal from the noise \
and produce a structured session record.

EXTRACT:
- DECISIONS: What was decided? Why? What alternatives were rejected?
- OUTCOMES: What was accomplished? What concretely changed in the codebase?
- DISCOVERIES: What was learned? What unexpected things were found?
- DEAD ENDS: What was tried and abandoned? Why did it fail?
- OPEN THREADS: What was started but not finished? What needs follow-up?

IGNORE:
- Routine file reads and exploration that led nowhere specific
- Tool usage patterns (nobody cares that Read was called 47 times)
- Intermediate steps that didn't produce insight or change anything

CLASSIFY significance:
- "low": Routine exploration, minor tweaks, no decisions made, nothing learned
- "medium": Meaningful work completed, files changed, bugs fixed
- "high": Decisions made, architecture changed, significant learnings, dead ends worth remembering

Return a JSON object with exactly these fields:
{
  "significance": "low" | "medium" | "high",
  "summary": "2-4 sentence narrative of the session arc",
  "decisions": ["Decision 1: chose X over Y because Z", ...],
  "outcomes": ["Completed X", "Changed Y in Z", ...],
  "discoveries": ["Found that X behaves like Y", ...],
  "dead_ends": ["Tried X but failed because Y", ...],
  "open_threads": ["Started X, needs follow-up on Y", ...]
}

Rules:
- summary should read like a handoff note — what would the next person need to know?
- Each array item should be a complete, specific sentence. Mention file names, service names, error messages.
- Empty arrays are fine — not every session has dead ends or discoveries.
- Be ruthless about significance: a session that only explored files is "low".
- Return ONLY the JSON object. No markdown fences, no explanation."""


def build_session_synthesis_messages(
    memories: list[dict], project: str, session_name: str,
) -> list[dict]:
    """Build messages for memory-based session synthesis (legacy path).

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


# ============================================================
# Query Classification Prompt (v0.28.0 — Type-Routed Retrieval)
# ============================================================

QUERY_CLASSIFICATION_SYSTEM_PROMPT = """\
You classify search queries by intent. Given a search query for a personal memory store, \
classify it into exactly one intent type.

Return a JSON object with exactly one field:
{"intent": "factual"}

Valid intents:
- "factual": Questions about facts, people, places, things. ("What did X say?", "Where does Y live?")
- "temporal": Questions about when things happened, sequences, timelines. ("When did we deploy?", "What happened last week?")
- "procedural": Questions about how to do something, processes, steps. ("How do I deploy?", "What's the command for X?")
- "exploratory": Open-ended research, pattern discovery, connections. ("What do we know about X?", "What patterns exist?")
- "debug": Troubleshooting, error investigation, fixing things. ("Why did X break?", "What caused the error?")

Return ONLY the JSON object. No markdown fences, no explanation."""


def build_query_classification_messages(query: str) -> list[dict]:
    """Build messages for query intent classification."""
    return [
        {"role": "system", "content": QUERY_CLASSIFICATION_SYSTEM_PROMPT},
        {"role": "user", "content": query},
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
