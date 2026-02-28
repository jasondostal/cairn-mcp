"""Multi-agent anti-pattern detection (ca-154).

Detects known multi-agent anti-patterns:
- Split Keel: Two agents touching the same file
- Drifting Anchorage: Scope expanding beyond original plan
- Skeleton Crew: Over-decomposition into trivially small tasks

Used by coordinators during decomposition and monitoring phases.
Starts as soft warnings — returns findings without blocking execution.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class AntiPatternFinding:
    """A detected anti-pattern instance."""

    pattern: str  # "split_keel", "drifting_anchorage", "skeleton_crew"
    severity: str  # "warning", "error"
    message: str
    affected_items: list[str] = field(default_factory=list)
    recommendation: str = ""

    def to_dict(self) -> dict:
        return {
            "pattern": self.pattern,
            "severity": self.severity,
            "message": self.message,
            "affected_items": self.affected_items,
            "recommendation": self.recommendation,
        }


# File path patterns commonly found in task descriptions
_FILE_PATH_RE = re.compile(
    r'(?:^|[\s`"\'])('
    r'(?:[a-zA-Z_][\w\-]*/)*'  # directory components
    r'[a-zA-Z_][\w\-]*\.[a-zA-Z]{1,10}'  # filename.ext
    r')(?:[\s`"\']|$|[,;:\)])',
    re.MULTILINE,
)


def extract_file_paths(text: str) -> set[str]:
    """Extract likely file paths from task description text."""
    if not text:
        return set()
    return {m.group(1) for m in _FILE_PATH_RE.finditer(text)}


def detect_split_keel(children: list[dict]) -> list[AntiPatternFinding]:
    """Detect Split Keel — two tasks that touch the same file.

    Examines task descriptions and titles for file path references.
    Two in-progress or open tasks referencing the same file is a conflict.
    """
    findings: list[AntiPatternFinding] = []

    # Map file → list of tasks that reference it
    file_to_tasks: dict[str, list[str]] = {}

    active_statuses = {"open", "ready", "in_progress"}
    for child in children:
        if child.get("status") not in active_statuses:
            continue
        display_id = child.get("display_id", "?")
        title = child.get("title", "")
        desc = child.get("description") or ""
        files = extract_file_paths(f"{title} {desc}")

        for f in files:
            file_to_tasks.setdefault(f, []).append(display_id)

    for filepath, tasks in file_to_tasks.items():
        if len(tasks) > 1:
            findings.append(AntiPatternFinding(
                pattern="split_keel",
                severity="warning",
                message=f"Multiple active tasks reference '{filepath}': {', '.join(tasks)}",
                affected_items=tasks,
                recommendation=(
                    f"Ensure only one agent modifies '{filepath}' at a time. "
                    "Consider sequencing these tasks or consolidating the file changes."
                ),
            ))

    return findings


def detect_drifting_anchorage(
    children: list[dict],
    original_count: int | None = None,
    drift_threshold: float = 1.5,
) -> list[AntiPatternFinding]:
    """Detect Drifting Anchorage — scope expanding beyond original plan.

    If current subtask count exceeds original_count by more than
    drift_threshold (default 1.5x), that's scope creep.
    """
    findings: list[AntiPatternFinding] = []
    current_count = len(children)

    if original_count is not None and original_count > 0:
        ratio = current_count / original_count
        if ratio > drift_threshold:
            findings.append(AntiPatternFinding(
                pattern="drifting_anchorage",
                severity="warning",
                message=(
                    f"Scope drift detected: {current_count} subtasks vs "
                    f"{original_count} originally planned "
                    f"(ratio: {ratio:.1f}x, threshold: {drift_threshold}x)"
                ),
                affected_items=[c.get("display_id", "?") for c in children],
                recommendation=(
                    "Consider whether the additional subtasks are truly necessary. "
                    "Set a human gate for scope re-approval if the epic has grown significantly."
                ),
            ))

    # Also flag if there are more than 10 subtasks regardless
    if current_count > 10:
        findings.append(AntiPatternFinding(
            pattern="drifting_anchorage",
            severity="warning",
            message=f"High subtask count: {current_count} subtasks under this epic",
            affected_items=[c.get("display_id", "?") for c in children],
            recommendation=(
                "Consider grouping related subtasks into sub-epics. "
                "Flat hierarchies with >10 items are hard for coordinators to manage."
            ),
        ))

    return findings


def detect_skeleton_crew(
    children: list[dict],
    min_description_length: int = 50,
) -> list[AntiPatternFinding]:
    """Detect Skeleton Crew — over-decomposition into trivial tasks.

    Tasks with very short descriptions (< min_description_length chars)
    are likely too small to warrant their own dispatch.
    """
    findings: list[AntiPatternFinding] = []
    trivial: list[str] = []

    for child in children:
        desc = child.get("description") or ""
        title = child.get("title", "")
        if len(desc) < min_description_length and len(title) < 30:
            trivial.append(child.get("display_id", "?"))

    if len(trivial) >= 2:
        findings.append(AntiPatternFinding(
            pattern="skeleton_crew",
            severity="warning",
            message=(
                f"{len(trivial)} subtask(s) appear trivially small: {', '.join(trivial)}. "
                "The overhead of dispatching an agent may exceed the work itself."
            ),
            affected_items=trivial,
            recommendation=(
                "Consider batching these into a single task, or having the "
                "coordinator handle them directly (trivial config changes are OK)."
            ),
        ))

    return findings


def analyze_epic(
    children: list[dict],
    original_count: int | None = None,
) -> dict:
    """Run all anti-pattern detections on an epic's children.

    Returns a summary with findings and an overall health assessment.
    """
    findings: list[AntiPatternFinding] = []

    findings.extend(detect_split_keel(children))
    findings.extend(detect_drifting_anchorage(children, original_count))
    findings.extend(detect_skeleton_crew(children))

    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]

    if errors:
        health = "unhealthy"
    elif warnings:
        health = "caution"
    else:
        health = "healthy"

    return {
        "health": health,
        "findings": [f.to_dict() for f in findings],
        "error_count": len(errors),
        "warning_count": len(warnings),
        "patterns_checked": ["split_keel", "drifting_anchorage", "skeleton_crew"],
    }
