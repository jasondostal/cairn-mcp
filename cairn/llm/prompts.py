"""Enrichment prompt template. Single LLM call for tags, importance, type, and summary."""

VALID_MEMORY_TYPES = [
    "note", "decision", "rule", "code-snippet", "learning",
    "research", "discussion", "progress", "task", "debug", "design",
]

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
