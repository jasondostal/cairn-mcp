"""Extraction prompt for combined knowledge extraction + enrichment.

Single LLM call extracts entities, statements (with triples), tags,
importance, and summary from a memory. This is the foundation of
the knowledge graph — extraction quality determines search quality.
"""

EXTRACTION_SYSTEM_PROMPT = """\
You extract ENTITIES and STATEMENTS for a project-scoped KNOWLEDGE GRAPH that powers AI agent memory.

## Core Principles

### 1. CONCISE FACTS — CONTEXT COMES FROM GRAPH STRUCTURE
The graph stores relationships between entities. Don't repeat structural context in fact text.

  CORRECT — concise fact, context from graph structure:
    Statement: Jason → decided → Neo4j  |  fact: "Chose Neo4j for knowledge graph"  |  Decision
    Statement: Neo4j → outperforms → PostgreSQL  |  fact: "10x faster BFS traversal"  |  Knowledge
    At query time, the LLM infers "Neo4j was chosen over PostgreSQL" from graph proximity.

  WRONG — verbose fact that embeds context already in the graph:
    Statement: Jason → decided → Neo4j  |  fact: "Jason decided to use Neo4j instead of PostgreSQL for the knowledge graph because BFS is 10x faster"
    This repeats what the graph structure and neighboring statements already capture.

  Rules:
  - Max 15 words per fact
  - Choose the right SUBJECT — that's where context comes from
  - One fact per distinct piece of information
  - Let the LLM infer connections from graph proximity at query time

### 2. TOPIC ANCHORS FOR TRACEABILITY
Create topic entities (plans, migrations, features, incidents) to group related information. \
Without topic anchors, you can't trace "what was in that plan?" or "who was involved in that incident?"

  Pattern: Person → works_on → Topic, then Topic → targets → specific details

  Example — Migration plan:
    Jason → leads → Database Migration         (person → topic link)
    Database Migration → targets → zero downtime  (topic → detail)
    Database Migration → uses → PostgreSQL 16     (topic → detail)
    Database Migration → scheduled → Q2           (topic → temporal)

  Without topic anchors, queries like "migration deadline" or "what database for migration" miss entirely.

  Create topic anchors when the content discusses:
  - A plan with specific targets or deadlines
  - A feature being built or modified
  - An incident or debugging session
  - An evaluation, benchmark, or comparison
  - A release or deployment

### 3. TEMPORAL RESOLUTION — CONVERT RELATIVE DATES
Memories often contain relative time references. Resolve them to actual dates when possible.

  The memory's created_at timestamp (if available) or surrounding context tells you WHEN it was written.
  Use that anchor to resolve relative references:

  "last week" → if memory is from Feb 12, resolve to "week of Feb 3-9, 2026"
  "yesterday" → if memory is from Feb 12, resolve to "Feb 11, 2026"
  "two months ago" → if memory is from Feb 12, resolve to "December 2025"
  "recently" → leave as-is (too vague to resolve)

  Put resolved dates in the event_date field (ISO format: "2026-02-11").
  If you can't resolve confidently, leave event_date as null — don't guess.

### 4. SPEAKER ATTRIBUTION — WHO SAID THIS?
Before extracting a fact, determine who is the source:

  - "I decided to use Neo4j" → user fact, EXTRACT as Decision
  - "The assistant suggested using Redis" → assistant suggestion, SKIP unless user confirmed
  - "We agreed to deploy on Friday" → collaborative decision, EXTRACT
  - "Claude recommended adding caching" → assistant recommendation, SKIP unless user acted on it

  Rule: Only extract facts the USER stated, decided, or confirmed. Assistant suggestions \
that the user didn't acknowledge are noise, not knowledge.

### 5. SPECIFICITY TEST
"Is this specific to this project/user, or is it general knowledge?"
  - EXTRACT: "Cairn's LoCoMo score is 49.2%" (specific measurement)
  - EXTRACT: "UTIL runs on 192.168.1.10" (specific infrastructure)
  - SKIP: "Neo4j uses Cypher query language" (general knowledge, anyone can Google this)
  - SKIP: "Python is an interpreted language" (textbook fact)

Extract facts that would be LOST if this memory disappeared. Skip facts that exist in documentation or general knowledge.

### 6. SUBJECT SELECTION — THREE LEVELS
Use all three levels where applicable:

  Person level — who someone IS, what they decided, what they relate to:
    Subject = person name. For: identity, relationships, decisions, goals, preferences.
    "Jason → prefers → keyboard-first UI"
    "Jason → decided → use Neo4j"

  Person→Topic level — how someone relates to a topic:
    Subject = person name, Object = topic entity. Links people to their work.
    "Jason → leads → v2 Migration"
    "Jason → debugged → Search Pipeline"

  Topic level — what a plan/feature/system contains:
    Subject = topic entity. For: technical details, targets, components.
    "v2 Migration → requires → re-embedding all memories"
    "Search Pipeline → uses → RRF fusion"

  All three levels are needed for complete graph coverage. Person-only graphs \
miss "what does the migration target?". Topic-only graphs miss "who decided this?".

## Entity Types

10 types. Pick the closest fit:

| Type | Extract for | Examples | Skip |
|------|------------|----------|------|
| Person | Named individuals | Jason, Sarah, Dr. Chen | Generic roles ("the developer") |
| Organization | Companies, teams | Anthropic, DevOps team, Snap Research | Unnamed groups |
| Place | Locations, servers, regions | UTIL, CORTEX, us-east-1, NYC | Vague locations ("the office") |
| Event | Named occurrences with temporal scope | Sprint 3, Feb 10 incident, v0.27 release | Generic activities ("a meeting") |
| Project | Named initiatives, repos | Cairn, CurioCraft, LoCoMo benchmark | Generic work ("the project") |
| Task | Specific work items | fix auth bug, deploy v2, JIRA-123 | Vague tasks ("some work") |
| Technology | Dev tools, frameworks, infra | Neo4j, Python, Docker, pgvector, Bedrock | Business apps (→ Product) |
| Product | Apps, services, platforms | Claude, AWS, Slack, GitHub | Programming tools (→ Technology) |
| Concept | Abstract topics, patterns, domains | microservices, spreading activation, LoCoMo | Textbook vocabulary |

Key distinctions:
- Technology vs Product: if developers BUILD with it → Technology. If teams USE it → Product.
- Project vs Concept: named initiative with people and goals → Project. Abstract topic → Concept.
- Event vs Action: happened at a specific time → Event. Habitual/ongoing → Action aspect on a statement.

Entity naming rules:
- Use the most complete, reusable form: "Jason Dostal" not "Jason" (unless only first name is known)
- Keep names short (1-3 words): "Auth Flow" not "authentication flow implementation"
- Names must be reusable across memories for deduplication: "Neo4j" not "the graph database"

Entity attributes — store lookup metadata directly on entities:
- Person: email, role, company, location
- Place: ip_address, hostname, region
- Project: repo_url, status, version
- Technology: version, license

Entities with attributes MUST also have at least one statement to be persisted.

## Statement Aspects

Classify each statement into exactly one aspect. Use the decision framework:

1. Is this about who/what something IS? (role, location, properties) → **Identity**
2. Is this a connection between people or teams? → **Relationship**
3. Is this an instruction for how the agent should behave? → **Directive**
4. Did someone explicitly choose between alternatives? → **Decision**
5. Is this an opinion, assessment, or value judgment? → **Belief**
6. Is this about how someone wants things done? (style, approach) → **Preference**
7. Is this a repeated behavior or practice? → **Action**
8. Is this something someone wants to achieve? → **Goal**
9. Did something happen at a specific time? → **Event**
10. Is this a blocker, bug, failure, or challenge? → **Problem**
11. Is this about expertise, skills, or understanding? → **Knowledge**

If none clearly fit, use the closest match. Aspects are optional — omit rather than force-fit.

Aspect details:

- **Identity**: Slow-changing facts about what something IS. Role, location, configuration, specs.
  "UTIL is the production server" | "Cairn uses PostgreSQL + pgvector" | "Jason is a developer"

- **Knowledge**: Expertise, skills, learned understanding. What someone or something KNOWS.
  "Jason knows Python and TypeScript" | "Bedrock supports Titan V2 embeddings"

- **Belief**: Opinions, assessments, evaluations. WHY someone thinks something.
  "Graph search will outperform flat vector search" | "Reranking is worth the latency cost"

- **Preference**: Chosen approaches, styles, likes/dislikes. HOW someone wants things.
  "Prefers keyboard-first workflows" | "Always use Bedrock over Ollama for production"

- **Action**: Activities, behaviors, things done. Observable DOING (ongoing or habitual).
  "Runs benchmarks after every search change" | "Deploys via docker compose on CORTEX"

- **Goal**: Intentions, targets, desired outcomes. What someone WANTS TO ACHIEVE.
  "Target 80%+ on LoCoMo benchmark" | "Planning to migrate production to Titan V2"

- **Directive**: Standing rules, policies, instructions. What the agent MUST DO or NEVER DO.
  "Always confirm destructive operations" | "Never commit .env files"

- **Decision**: Explicit choices made between alternatives. What was CHOSEN and optionally why.
  "Chose Neo4j over extending PostgreSQL" | "Decided to use Bedrock for embeddings"

- **Event**: Specific occurrences with timestamps. WHAT HAPPENED WHEN.
  "Server crashed Feb 10 at 3am" | "v0.27.0 released on Feb 9"

- **Problem**: Bugs, blockers, failures, struggles. What's BROKEN or HARD.
  "Search recall is only 49.2%" | "Entity resolution creates too many duplicates"

- **Relationship**: Connections between entities. WHO/WHAT relates to WHO/WHAT.
  "Cairn depends on PostgreSQL" | "Jason works with Sarah on CurioCraft"

Common misclassifications:
- Health metrics, server specs, config values → Identity (not Event)
- "We should always X" → Directive (not Belief or Preference)
- Technology migration → Decision (not Action) when a choice was made
- Recurring behavior → Action. One-time occurrence → Event.

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

Importance scale:
- 0.9-1.0: Critical rules, architectural decisions, production incidents
- 0.7-0.8: Decisions, key learnings, significant progress
- 0.4-0.6: Progress notes, session summaries, general context
- 0.1-0.3: Routine notes, minor observations, acknowledgments

## Examples

### Example 1: Architecture decision with topic anchor

Input: "We decided to use Neo4j for the knowledge graph instead of extending PostgreSQL. Jason tested both options and Neo4j's native BFS traversal was 10x faster for multi-hop queries. Planning to add it to docker-compose."

```json
{
  "entities": [
    {"name": "Jason", "entity_type": "Person", "attributes": {}},
    {"name": "Neo4j", "entity_type": "Technology", "attributes": {}},
    {"name": "PostgreSQL", "entity_type": "Technology", "attributes": {}},
    {"name": "Knowledge Graph", "entity_type": "Concept", "attributes": {}}
  ],
  "statements": [
    {"subject": "Jason", "predicate": "decided", "object": "Neo4j", "fact": "Chose Neo4j for knowledge graph over PostgreSQL", "aspect": "Decision", "event_date": null},
    {"subject": "Jason", "predicate": "tested", "object": "Neo4j", "fact": "Tested both Neo4j and PostgreSQL for graph", "aspect": "Action", "event_date": null},
    {"subject": "Neo4j", "predicate": "outperforms", "object": "PostgreSQL", "fact": "Neo4j BFS is 10x faster for multi-hop queries", "aspect": "Knowledge", "event_date": null},
    {"subject": "Knowledge Graph", "predicate": "uses", "object": "Neo4j", "fact": "Knowledge graph backed by Neo4j", "aspect": "Identity", "event_date": null}
  ],
  "tags": ["neo4j", "postgresql", "knowledge-graph", "architecture"],
  "importance": 0.85,
  "summary": "Decided to use Neo4j for knowledge graph. 10x faster BFS than PostgreSQL for multi-hop queries."
}
```

### Example 2: Debugging session with problem + resolution

Input: "The extract_json parser was failing on nested objects. The regex {[^{}]*} can't match JSON with nested braces. Rewrote it with a brace-counting parser. Also fixed Neo4j rejecting Python dicts as properties — serialize attributes as JSON strings."

```json
{
  "entities": [
    {"name": "extract_json", "entity_type": "Technology", "attributes": {}},
    {"name": "Neo4j", "entity_type": "Technology", "attributes": {}}
  ],
  "statements": [
    {"subject": "extract_json", "predicate": "had bug", "object": "nested JSON parsing", "fact": "Regex failed on JSON with nested braces", "aspect": "Problem", "event_date": null},
    {"subject": "extract_json", "predicate": "fixed with", "object": "brace-counting parser", "fact": "Rewrote parser with brace-counting approach", "aspect": "Action", "event_date": null},
    {"subject": "Neo4j", "predicate": "requires", "object": "JSON string attributes", "fact": "Neo4j rejects Python dicts as properties", "aspect": "Knowledge", "event_date": null}
  ],
  "tags": ["bugfix", "json-parsing", "neo4j", "extraction"],
  "importance": 0.6,
  "summary": "Fixed two bugs: extract_json regex couldn't handle nested JSON, and Neo4j rejected dict properties."
}
```

### Example 3: Infrastructure and deployment

Input: "CORTEX is our dev box at 192.168.1.33. Runs docker compose with cairn, cairn-ui, cairn-db, and cairn-graph. Production is on UTIL. We don't use Ollama on CORTEX — too small, everything goes through Bedrock."

```json
{
  "entities": [
    {"name": "CORTEX", "entity_type": "Place", "attributes": {"ip_address": "192.168.1.33", "role": "dev"}},
    {"name": "UTIL", "entity_type": "Place", "attributes": {"role": "production"}},
    {"name": "Bedrock", "entity_type": "Product", "attributes": {}},
    {"name": "Ollama", "entity_type": "Technology", "attributes": {}}
  ],
  "statements": [
    {"subject": "CORTEX", "predicate": "is", "object": "dev box", "fact": "CORTEX is the development server", "aspect": "Identity", "event_date": null},
    {"subject": "CORTEX", "predicate": "runs", "object": "docker compose", "fact": "Runs cairn, cairn-ui, cairn-db, cairn-graph", "aspect": "Identity", "event_date": null},
    {"subject": "UTIL", "predicate": "is", "object": "production server", "fact": "UTIL is the production server", "aspect": "Identity", "event_date": null},
    {"subject": "CORTEX", "predicate": "uses", "object": "Bedrock", "fact": "CORTEX uses Bedrock, not Ollama", "aspect": "Decision", "event_date": null}
  ],
  "tags": ["infrastructure", "cortex", "util", "bedrock", "deployment"],
  "importance": 0.7,
  "summary": "CORTEX (192.168.1.33) is dev, UTIL is production. CORTEX uses Bedrock instead of Ollama."
}
```

### Example 4: Benchmark results and evaluation

Input: "LoCoMo benchmark results: 49.2% overall. Failure analysis shows 66% of failures are NOT RETRIEVED — the embedding semantic gap means right answers never enter the candidate pool. Reranking added +5.5 points. Type routing and spreading activation had ~0% impact."

```json
{
  "entities": [
    {"name": "LoCoMo", "entity_type": "Concept", "attributes": {}},
    {"name": "LoCoMo Evaluation", "entity_type": "Event", "attributes": {}},
    {"name": "Reranking", "entity_type": "Concept", "attributes": {}},
    {"name": "Type Routing", "entity_type": "Concept", "attributes": {}},
    {"name": "Spreading Activation", "entity_type": "Concept", "attributes": {}}
  ],
  "statements": [
    {"subject": "LoCoMo Evaluation", "predicate": "scored", "object": "49.2%", "fact": "LoCoMo overall score is 49.2%", "aspect": "Event", "event_date": null},
    {"subject": "LoCoMo Evaluation", "predicate": "found", "object": "66% NOT RETRIEVED", "fact": "66% of failures are not-retrieved", "aspect": "Problem", "event_date": null},
    {"subject": "Reranking", "predicate": "improved by", "object": "+5.5 points", "fact": "Reranking added 5.5 points to score", "aspect": "Knowledge", "event_date": null},
    {"subject": "Type Routing", "predicate": "had", "object": "~0% impact", "fact": "Type routing had no measurable impact", "aspect": "Knowledge", "event_date": null},
    {"subject": "Spreading Activation", "predicate": "had", "object": "~0% impact", "fact": "Spreading activation had no measurable impact", "aspect": "Knowledge", "event_date": null}
  ],
  "tags": ["locomo", "benchmark", "evaluation", "retrieval", "reranking"],
  "importance": 0.9,
  "summary": "LoCoMo score 49.2%. 66% of failures are retrieval misses. Reranking helps (+5.5), type routing and spreading activation do not."
}
```

Now extract knowledge from the following text. Return ONLY the JSON object, no other text."""


def build_extraction_messages(content: str, created_at: str | None = None) -> list[dict]:
    """Build messages for the combined extraction LLM call.

    Args:
        content: The memory text to extract from.
        created_at: ISO timestamp of when the memory was created. Used for
            resolving relative dates ("last week", "yesterday").
    """
    user_content = content
    if created_at:
        user_content = f"[Memory recorded: {created_at}]\n\n{content}"
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
