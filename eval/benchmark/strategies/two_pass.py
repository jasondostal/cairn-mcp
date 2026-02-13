"""Two-pass ingestion strategy: normalize → extract.

Pass 1 (NORMALIZE): Conversation → clean, attributed narrative.
  - Resolves pronouns ("she" → "Melanie")
  - Resolves relative dates ("last year" → "2022")
  - Attributes speakers (who said what)
  - Preserves specific details (names, titles, numbers, dates)

Pass 2 (EXTRACT): Normalized narrative → structured facts with aspects.
  - Entities with types
  - Facts with aspect classification (Identity, Preference, Event, etc.)
  - Event dates as separate field
  - Tags for label-based search scoping

Two-pass approach improves fact density and detail preservation over single-pass extraction.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from cairn.core.utils import extract_json
from eval.benchmark.base import BenchmarkSession, IngestStrategy

if TYPE_CHECKING:
    from cairn.core.memory import MemoryStore
    from cairn.llm.interface import LLMInterface

logger = logging.getLogger(__name__)

# ─── Pass 1: Normalization ───────────────────────────────────────────

NORMALIZE_SYSTEM = """\
You are a conversation normalizer for a personal memory system. Transform raw \
conversation into enriched, information-dense statements.

CRITICAL: CAPTURE ALL DISTINCT PIECES OF INFORMATION. Every separate fact, \
preference, event, detail, name, title, number, or date mentioned must be \
preserved. Missing information is unacceptable.

## Speaker Attribution (CRITICAL)

Conversations have TWO speakers with DIFFERENT fact authority:

USER STATEMENTS → Become user facts:
- Direct statements: "I want X", "My goal is Y", "I prefer Z"
- Reports: "I completed X", "I went to Y", "I read Z"
- Confirmations of suggestions: "Yes", "Sounds good", "Let's do that"

ASSISTANT STATEMENTS → Generally NOT user facts:
- Suggestions: "You could try X", "I recommend Y"
- Questions: "Want me to help with X?"
- Information provided: "Here's what I found about X"
- Coaching/guidance: "Here's how to do X"

RULES:
1. User statements → Normalize as user facts: "{speaker_a} prefers X"
2. User confirms assistant suggestion → User decision: "{speaker_a} decided to X"
3. Assistant offers WITHOUT user confirmation → "{speaker_b} suggested X" (NOT a user fact)
4. Assistant provides information → "{speaker_b} mentioned X" or "{speaker_b} explained X"
5. User silence ≠ agreement. No response means the offer is pending, NOT accepted.

## Enrichment Rules

1. SPEAKER ATTRIBUTION: Always use full names, never pronouns. \
Replace "I", "she", "he", "they" with actual names.

2. TEMPORAL RESOLUTION: Convert ALL relative dates using the session date. \
"yesterday" → exact date. "last year" → exact year. "last Friday" → exact date. \
"3 years ago" → exact year. Add date prefix ONCE at the start, not on every sentence.

3. PRESERVE EXACT DETAILS: Book titles, song names, place names, numbers, \
percentages, prices, specific words — keep EXACTLY as stated. Never generalize. \
"I read 'Nothing Is Impossible'" → keep the exact title. \
"the song 'Brave' by Sara Bareilles" → keep title AND artist. \
"31% body fat" → keep exact number.

4. MULTI-FACT SPLITTING: Break lists and compound statements into separate sentences. \
"I like pottery, camping, painting, and swimming" → FOUR separate sentences: \
"{speaker_a} likes pottery." "{speaker_a} likes camping." etc. \
"I prefer X, Y, and avoid Z" → "{speaker_a} prefers X. {speaker_a} prefers Y. {speaker_a} avoids Z."

5. SEMANTIC ENRICHMENT: Add synonyms/related terms in parentheses for better search. \
"my address" → "residential address (home location)" \
"my job" → "position (role, employment)" \
"my favorite song" → "favorite song (music preference)"

6. IMPLICIT FACTS: Derive facts from context. \
"I've been doing pottery for 3 years" (July 2023) → "has been doing pottery since 2020." \
"My three kids" → explicitly state the person has 3 children. \
"We went as a family" → name who was there if known.

7. RELATIONSHIPS: Preserve all connections with explicit roles. \
"My sister Sarah" → "{speaker_a}'s sister is Sarah." \
"My kids" → "{speaker_a}'s children" (and count if known). \
"My friend from work" → preserve the relationship context.

8. EMOTIONAL/EXPERIENTIAL DETAILS: Preserve how people felt, what they experienced. \
"It was scary but we got through it" → preserve both the fear and the resilience. \
"I was so proud" → preserve the emotion and what triggered it.

9. VISUAL/PHYSICAL DETAILS: Capture specific descriptions. \
"a painting with pink skies" → preserve "pink skies" detail. \
"a black and white bowl" → preserve the color description. \
"wearing a necklace that symbolizes strength" → preserve the symbolism.

## Skip Rules

SKIP only: Pure greetings ("hi", "bye"), empty pleasantries ("how are you"), \
standalone acknowledgments ("ok", "got it") with NO topic reference.

DO NOT SKIP: Encouragement that references specific activities, emotional exchanges \
about specific events, details about hobbies/interests/experiences.

## Output Format

One fact per line. Plain text, no bullet points, no numbering. \
Each sentence self-contained and understandable without context. \
Use full names, never pronouns."""

NORMALIZE_USER = """\
Session date: {date}
Speakers: {speaker_a} (user), {speaker_b} (assistant)

Conversation:
{conversation}

Rewrite this conversation as a normalized factual narrative."""


# ─── Pass 2: Extraction ─────────────────────────────────────────────

EXTRACT_SYSTEM = """\
You are a knowledge extraction system. Extract structured facts from a normalized \
conversation narrative. Each fact becomes a searchable memory.

## Extraction Logic

For EACH piece of information, ask:
1. WHO said this? → If the assistant said it and the user didn't confirm, SKIP it.
2. WHO is this about? → Use their full name.
3. WHAT is being said? → That's your fact content.
4. Is this SPECIFIC to this person? → Generic wisdom ("exercise is healthy") → SKIP.

## Speaker Attribution (CRITICAL)

The normalized text distinguishes user statements from assistant statements.

DETECTION PATTERNS:
- "[Name] said/wants/prefers/decided/went/attended" → User fact → EXTRACT
- "The assistant suggested/offered/provided/explained" → Assistant content → usually SKIP
- "[Name] confirmed/agreed/decided after suggestion" → User decision → EXTRACT

RULES:
1. User stated something → Extract as user fact
2. User confirmed assistant suggestion → Extract as user Decision
3. Assistant suggested but user didn't confirm → SKIP (not a user fact)
4. Assistant provided information → SKIP unless user acted on it

## Aspect Classification

Classify each fact. Ask these questions in order:

- Is this about who someone IS? (name, role, age, identity) → **Identity**
- Is this a connection between people? (family, friends, colleagues) → **Relationship**
- Did they explicitly CHOOSE between alternatives? → **Decision**
- Are they expressing an opinion or value? → **Belief**
- Is this about how they want things / what they like? → **Preference**
- Is this a repeated behavior or hobby? → **Action**
- Is this something they want to achieve? → **Goal**
- Did something happen at a specific time? → **Event** (MUST include event_date)
- Is this a blocker, challenge, or setback? → **Problem**
- What someone knows or learned? → **Knowledge**
- A rule, instruction, or promise? → **Directive**

COMMON MISCLASSIFICATIONS TO AVOID:
- "Has 3 children" → Identity (not Relationship)
- "Favorite song is Brave" → Preference (not Knowledge)
- "Has been doing pottery since 2020" → Action (ongoing), not Event
- "Went to a parade on July 1" → Event (specific time)
- "Likes pottery" → Preference. "Does pottery regularly" → Action.
- "Was scared but resilient" → the emotion is part of the Event context, include it in the fact

## Output Format

Return a JSON array. Extract EVERY distinct fact — 20-50 facts per session is normal.

[
  {
    "content": "Specific, self-contained fact with full names and dates. Max 20 words.",
    "aspect": "Event",
    "event_date": "2023-07-01",
    "importance": 0.7,
    "tags": ["pride", "lgbtq", "parade"],
    "entities": ["Caroline"]
  }
]

## Field Rules

- **content**: Self-contained sentence. Full names, no pronouns. Include specific \
details (exact titles, numbers, names, colors, places). Max ~20 words.
- **event_date**: ISO date (YYYY-MM-DD) ONLY for Event aspect. Null for everything else. \
If approximate, use what's known: "2022" → "2022-01-01", "July 2023" → "2023-07-01".
- **entities**: All named entities in this fact (people, places, organizations, songs, books, etc.)
- **importance**: 0.3=trivial, 0.5=normal, 0.7=significant, 0.9=critical life event
- **tags**: 2-5 topical tags for search. Include synonyms. \
"pottery" → ["pottery", "ceramics", "art", "hobby"]. \
"adoption" → ["adoption", "family", "parenting"].

## Critical Rules

- Extract EVERY distinct fact. One fact per piece of information. \
"Melanie likes pottery, painting, and camping" → THREE separate facts.
- NEVER drop specific details: exact song titles, book titles, names, numbers, dates, colors.
- NEVER merge multiple facts into one. One fact = one searchable unit.
- Include emotional context when relevant: "Caroline felt proud after her speech" not just "Caroline gave a speech".
- Preserve quantities: "3 children", "4 years of friendship", "$450 rent".
- For activities mentioned without dates, classify as Action (ongoing) not Event."""

EXTRACT_USER = """\
Session date: {date}

Normalized narrative:
{narrative}

Extract all facts as a JSON array."""


class TwoPassStrategy(IngestStrategy):
    """Two-pass ingestion: normalize conversations, then extract structured facts."""

    def __init__(self, llm: LLMInterface, max_turns_per_call: int = 50):
        self.llm = llm
        self.max_turns_per_call = max_turns_per_call

    @property
    def name(self) -> str:
        return "two_pass"

    def ingest(
        self,
        sessions: list[BenchmarkSession],
        memory_store: MemoryStore,
        project: str,
    ) -> dict:
        start = time.time()
        total_memories = 0
        total_extracted = 0
        errors = 0

        for session in sessions:
            try:
                facts = self._process_session(session)
                total_extracted += len(facts)

                for fact in facts:
                    content = fact["content"]
                    # Prepend date if not already present
                    if session.date and session.date not in content:
                        content = f"[{session.date}] {content}"

                    memory_store.store(
                        content=content,
                        project=project,
                        memory_type="note",
                        importance=fact.get("importance", 0.5),
                        tags=fact.get("tags", []) + [f"session:{session.session_id}"],
                        session_name=session.session_id,
                        enrich=False,  # two-pass already extracts tags/importance
                    )
                    total_memories += 1

                logger.debug(
                    "Session %s: %d facts extracted",
                    session.session_id,
                    len(facts),
                )
            except Exception:
                logger.exception("Two-pass failed for session %s", session.session_id)
                errors += 1

        duration = time.time() - start
        logger.info(
            "TwoPass: %d memories from %d sessions in %.1fs (%d errors)",
            total_memories,
            len(sessions),
            duration,
            errors,
        )
        return {
            "memory_count": total_memories,
            "extracted_facts": total_extracted,
            "sessions_processed": len(sessions),
            "errors": errors,
            "duration_s": round(duration, 2),
        }

    def _process_session(self, session: BenchmarkSession) -> list[dict]:
        """Two-pass pipeline: normalize → extract."""
        conversation = self._format_conversation(session)

        # Detect speaker names from the session
        speaker_a, speaker_b = self._detect_speakers(session)

        # Pass 1: Normalize
        narrative = self._normalize(conversation, session.date, speaker_a, speaker_b)
        if not narrative or narrative.strip() == "":
            logger.warning("Session %s: normalization returned empty", session.session_id)
            return []

        # Pass 2: Extract
        facts = self._extract(narrative, session.date)
        return facts

    def _normalize(
        self, conversation: str, date: str | None,
        speaker_a: str, speaker_b: str,
    ) -> str:
        """Pass 1: Normalize conversation into clean factual narrative."""
        messages = [
            {"role": "system", "content": NORMALIZE_SYSTEM},
            {
                "role": "user",
                "content": NORMALIZE_USER.format(
                    date=date or "unknown",
                    speaker_a=speaker_a,
                    speaker_b=speaker_b,
                    conversation=conversation,
                ),
            },
        ]
        return self.llm.generate(messages, max_tokens=4096)

    def _extract(self, narrative: str, date: str | None) -> list[dict]:
        """Pass 2: Extract structured facts from normalized narrative."""
        messages = [
            {"role": "system", "content": EXTRACT_SYSTEM},
            {
                "role": "user",
                "content": EXTRACT_USER.format(
                    date=date or "unknown",
                    narrative=narrative,
                ),
            },
        ]
        response = self.llm.generate(messages, max_tokens=4096)
        facts = extract_json(response, json_type="array")

        if not isinstance(facts, list):
            logger.warning("Extraction returned %s instead of list", type(facts))
            return []

        # Validate
        valid = []
        for fact in facts:
            if isinstance(fact, dict) and fact.get("content"):
                # Ensure aspect is valid
                if fact.get("aspect") not in {
                    "Identity", "Preference", "Action", "Event", "Goal",
                    "Decision", "Knowledge", "Belief", "Relationship",
                    "Problem", "Directive",
                }:
                    fact["aspect"] = "Knowledge"
                valid.append(fact)

        return valid

    def _detect_speakers(self, session: BenchmarkSession) -> tuple[str, str]:
        """Detect speaker names from session turns."""
        names = set()
        for turn in session.turns[:10]:
            role = turn.get("role", "")
            speaker = turn.get("speaker", "")
            if speaker:
                names.add(speaker)
        names_list = sorted(names)
        if len(names_list) >= 2:
            return names_list[0], names_list[1]
        elif len(names_list) == 1:
            return names_list[0], "Assistant"
        return "User", "Assistant"

    def _format_conversation(self, session: BenchmarkSession) -> str:
        """Format session turns as readable conversation."""
        turns = session.turns[:self.max_turns_per_call]
        parts = []
        for turn in turns:
            speaker = turn.get("speaker", turn.get("role", "User"))
            content = turn.get("content", turn.get("text", ""))
            parts.append(f"{speaker}: {content}")
        return "\n".join(parts)
