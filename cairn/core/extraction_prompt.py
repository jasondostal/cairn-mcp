"""Extraction prompt for combined knowledge extraction + enrichment.

Single LLM call extracts entities, statements (with triples), tags,
importance, and summary from a memory. This is the foundation of
the knowledge graph — extraction quality determines search quality.
"""

EXTRACTION_SYSTEM_PROMPT = """\
You extract ENTITIES and STATEMENTS for a project-scoped KNOWLEDGE GRAPH that powers AI agent memory.

## Extraction Logic

For each piece of information, ask:
1. WHO SAID this? → If assistant suggested it and user didn't confirm, SKIP.
2. WHO/WHAT is it about? → That's your SUBJECT.
3. WHAT is being said? → That's your PREDICATE + OBJECT.
4. Is it specific to this project/user? → If general knowledge anyone can Google, SKIP.

## Principles

**CONCISE FACTS** — Max 15 words per fact. Context comes from graph structure (subject → predicate → object), not from repeating it in fact text. One fact per distinct piece of information.

**TOPIC ANCHORS** — Create topic entities (plans, features, incidents, evaluations, releases) to group related statements. Pattern: Person → works_on → Topic, then Topic → targets → details. Without anchors, queries like "migration deadline" miss entirely.

**SUBJECT SELECTION** — Use all three levels:
- Person level: who decided/prefers/is (Identity, Decision, Preference, Goal)
- Person→Topic: who leads/works on what (Goal, Action, Decision)
- Topic level: what a plan/system contains (technical details, targets, components)

**TEMPORAL RESOLUTION** — Convert relative dates using the memory's timestamp. "last week" from Feb 12 → "week of Feb 3-9, 2026". Put resolved dates in event_date (ISO format). Leave null if unresolvable.

**SPEAKER ATTRIBUTION** — [Speaker: user] = extract with full confidence. [Speaker: assistant] = extract confirmed findings only, skip unacted-on suggestions. No tag = infer: "I decided X" → user fact. "Claude suggested X" → skip unless confirmed.

## Entity Types

10 types — pick the closest fit:

| Type | Examples |
|------|----------|
| Person | Alice, Dr. Chen |
| Organization | Anthropic, DevOps team |
| Place | prod-1, us-east-1, staging |
| Event | Sprint 3, v0.27 release |
| Project | Cairn, Acme App |
| Task | fix auth bug, JIRA-123 |
| Technology | Neo4j, Docker, pgvector |
| Product | Claude, AWS, Slack |
| Concept | microservices, LoCoMo |

Technology = developers BUILD with it. Product = teams USE it.
Names: most complete reusable form, 1-3 words. "Neo4j" not "the graph database".
Attributes: Person (email, role), Place (ip_address, hostname), Project (repo_url, version), Technology (version).
Entities with attributes MUST also have at least one statement.

## Statement Aspects

Classify each statement into one aspect using this decision tree:

1. Who/what something IS? (role, config, specs) → **Identity**
2. Connection between entities? → **Relationship**
3. Agent behavior instruction? → **Directive**
4. Chose between alternatives? → **Decision**
5. Opinion or value judgment? → **Belief**
6. Preferred style/approach? → **Preference**
7. Repeated behavior/practice? → **Action**
8. Desired outcome? → **Goal**
9. Specific time occurrence? → **Event**
10. Blocker, bug, failure? → **Problem**
11. Expertise or understanding? → **Knowledge**

Omit rather than force-fit. Common mistakes: config/specs → Identity (not Event). "Always X" → Directive (not Belief). Tech migration choice → Decision (not Action). Recurring → Action, one-time → Event.

## Output Format

Return a JSON object:
```json
{
  "entities": [
    {"name": "...", "entity_type": "Person|Organization|...", "attributes": {}}
  ],
  "statements": [
    {
      "subject": "entity name (must match an extracted entity)",
      "predicate": "verb or relationship",
      "object": "entity name OR literal value",
      "fact": "natural language, max 15 words",
      "aspect": "Identity|Knowledge|...|null",
      "event_date": "ISO date or null"
    }
  ],
  "tags": ["lowercase", "keyword", "tags"],
  "importance": 0.5,
  "summary": "1-2 sentence summary."
}
```

Importance: 0.9-1.0 critical decisions/incidents, 0.7-0.8 key learnings, 0.4-0.6 progress notes, 0.1-0.3 minor observations.

## Examples

### Example 1: Architecture decision with topic anchor

Input: "We decided to use Neo4j for the knowledge graph instead of extending PostgreSQL. Alice tested both and Neo4j's BFS was 10x faster for multi-hop queries."

```json
{
  "entities": [
    {"name": "Alice", "entity_type": "Person", "attributes": {}},
    {"name": "Neo4j", "entity_type": "Technology", "attributes": {}},
    {"name": "PostgreSQL", "entity_type": "Technology", "attributes": {}},
    {"name": "Knowledge Graph", "entity_type": "Concept", "attributes": {}}
  ],
  "statements": [
    {"subject": "Alice", "predicate": "decided", "object": "Neo4j", "fact": "Chose Neo4j for knowledge graph over PostgreSQL", "aspect": "Decision", "event_date": null},
    {"subject": "Neo4j", "predicate": "outperforms", "object": "PostgreSQL", "fact": "Neo4j BFS 10x faster for multi-hop queries", "aspect": "Knowledge", "event_date": null},
    {"subject": "Knowledge Graph", "predicate": "uses", "object": "Neo4j", "fact": "Knowledge graph backed by Neo4j", "aspect": "Identity", "event_date": null}
  ],
  "tags": ["neo4j", "postgresql", "knowledge-graph", "architecture"],
  "importance": 0.85,
  "summary": "Decided to use Neo4j for knowledge graph. 10x faster BFS than PostgreSQL."
}
```

### Example 2: Infrastructure and deployment

Input: "staging is our dev box at 198.51.100.10. Runs docker compose with cairn, cairn-db, cairn-graph. Production is on prod-1. Everything goes through Bedrock."

```json
{
  "entities": [
    {"name": "staging", "entity_type": "Place", "attributes": {"ip_address": "198.51.100.10", "role": "dev"}},
    {"name": "prod-1", "entity_type": "Place", "attributes": {"role": "production"}},
    {"name": "Bedrock", "entity_type": "Product", "attributes": {}}
  ],
  "statements": [
    {"subject": "staging", "predicate": "is", "object": "dev box", "fact": "staging is the development server", "aspect": "Identity", "event_date": null},
    {"subject": "staging", "predicate": "runs", "object": "docker compose", "fact": "Runs cairn, cairn-db, cairn-graph", "aspect": "Identity", "event_date": null},
    {"subject": "staging", "predicate": "uses", "object": "Bedrock", "fact": "All LLM calls via Bedrock", "aspect": "Decision", "event_date": null}
  ],
  "tags": ["infrastructure", "staging", "production", "bedrock"],
  "importance": 0.7,
  "summary": "staging (198.51.100.10) is dev, prod-1 is production. All LLM via Bedrock."
}
```

Now extract knowledge from the following text. Return ONLY the JSON object, no other text."""


def build_extraction_messages(
    content: str,
    created_at: str | None = None,
    author: str | None = None,
    known_entities: list[dict] | None = None,
) -> list[dict]:
    """Build messages for the combined extraction LLM call.

    Args:
        content: The memory text to extract from.
        created_at: ISO timestamp of when the memory was created. Used for
            resolving relative dates ("last week", "yesterday").
        author: Voice attribution ("user", "assistant", "collaborative").
            Passed as [Speaker] tag to guide extraction filtering.
        known_entities: Existing entity names/types for canonicalization.
            When provided, appended to guide the LLM to reuse existing names.
    """
    user_content = content
    metadata_parts = []
    if created_at:
        metadata_parts.append(f"[Memory recorded: {created_at}]")
    if author:
        metadata_parts.append(f"[Speaker: {author}]")
    if metadata_parts:
        user_content = "\n".join(metadata_parts) + f"\n\n{content}"

    # Append known entities for canonicalization
    if known_entities:
        entity_list = ", ".join(
            f"{e['name']} ({e['entity_type']})" for e in known_entities[:100]
        )
        user_content += (
            f"\n\n[Known entities in this project: {entity_list}]\n"
            "Use these exact names when referring to known entities. "
            "Only create new entities for genuinely new concepts."
        )

    return [
        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def build_extraction_retry_messages(content: str, error: str) -> list[dict]:
    """Build messages for retry after parse failure."""
    return [
        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": content},
        {
            "role": "assistant",
            "content": f"I'll extract the knowledge... {error[:200]}",
        },
        {
            "role": "user",
            "content": (
                f"Your previous response was not valid JSON. Error: {error}\n\n"
                "Please try again. Return ONLY the JSON object."
            ),
        },
    ]
