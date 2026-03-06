"""Architecture boundary rule engine.

Loads rules from a YAML file (or string) and evaluates them against actual
imports extracted from source files or the Neo4j code graph. Reports violations.

Rule format (architecture.yaml):

    boundaries:
      - name: core-no-server
        description: Core must not depend on server
        from: "cairn.core.**"
        deny: "cairn.server"

      - name: neo4j-isolated
        description: Neo4j only in graph module
        deny: "neo4j"
        allow: "cairn.graph.**"

    contracts:
      - module: "cairn.graph.interface"
        exports: ["GraphProvider"]

Each boundary rule says: files matching ``from`` (default: all files) must NOT
import anything matching ``deny``, UNLESS the importing file matches ``allow``.

Each contract declares the public API surface of a module. Any ``from X import Y``
where Y is not in the declared exports list is a contract violation.

Patterns use fnmatch-style globs:
  - ``cairn.core.**``  matches ``cairn.core.search``, ``cairn.core.services``
  - ``cairn.core.*``   matches ``cairn.core.search`` but NOT ``cairn.core.sub.mod``
  - ``neo4j``          matches exactly ``neo4j``
"""

from __future__ import annotations

import fnmatch
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml  # type: ignore[import-untyped]

from cairn.code.imports import FileImports, extract_imports_from_directory

if TYPE_CHECKING:
    from cairn.graph.interface import GraphProvider

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Violation:
    """A single architecture boundary violation."""
    rule_name: str
    file_path: Path
    imported_module: str
    lineno: int
    description: str = ""


@dataclass(frozen=True)
class ContractViolation:
    """A single integration contract violation."""
    rule_module: str       # module declaring the contract
    consumer_file: str     # file that violated the contract
    imported_name: str     # name imported that isn't in exports
    lineno: int


@dataclass
class IntegrationContract:
    """Declared public API surface of a module."""
    module: str            # dotted module path
    exports: list[str]     # declared public names


@dataclass
class BoundaryRule:
    """One boundary rule from the architecture config."""
    name: str
    deny: list[str]              # Glob patterns for denied imports
    from_patterns: list[str]     # Files this rule applies to (empty = all)
    allow_patterns: list[str]    # Files exempt from this rule
    description: str = ""

    def applies_to(self, module_path: str) -> bool:
        """Does this rule apply to a file with the given module path?"""
        if not self.from_patterns:
            return True
        return any(_match(module_path, pat) for pat in self.from_patterns)

    def is_allowed(self, module_path: str) -> bool:
        """Is this file exempt from the rule?"""
        return any(_match(module_path, pat) for pat in self.allow_patterns)

    def is_denied(self, imported: str) -> bool:
        """Does this import match a denied pattern?"""
        return any(_match(imported, pat) for pat in self.deny)


@dataclass
class ArchConfig:
    """Parsed architecture configuration."""
    boundaries: list[BoundaryRule] = field(default_factory=list)
    contracts: list[IntegrationContract] = field(default_factory=list)
    source_path: Path | None = None


@dataclass
class ArchReport:
    """Results of an architecture check."""
    violations: list[Violation] = field(default_factory=list)
    contract_violations: list[ContractViolation] = field(default_factory=list)
    files_checked: int = 0
    rules_evaluated: int = 0
    parse_errors: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return len(self.violations) == 0 and len(self.contract_violations) == 0

    def summary(self) -> str:
        total = len(self.violations) + len(self.contract_violations)
        if self.clean:
            return f"Clean. {self.files_checked} files, {self.rules_evaluated} rules, 0 violations."
        lines = [f"{total} violation(s) in {self.files_checked} files:"]
        for v in self.violations:
            lines.append(f"  [{v.rule_name}] {v.file_path}:{v.lineno} imports {v.imported_module}")
        for cv in self.contract_violations:
            lines.append(
                f"  [contract:{cv.rule_module}] {cv.consumer_file}:{cv.lineno} "
                f"imports undeclared '{cv.imported_name}'"
            )
        return "\n".join(lines)


def _match(value: str, pattern: str) -> bool:
    """Match a module/file path against a glob pattern.

    Supports ``**`` for recursive matching:
      cairn.core.**  → matches cairn.core, cairn.core.x, cairn.core.x.y
      cairn.core.*   → matches cairn.core.x but not cairn.core.x.y
    """
    # Exact match
    if value == pattern:
        return True
    # ** matches any depth of dot-separated segments
    if "**" in pattern:
        base = pattern.replace(".**", "")
        if value == base:
            return True
        return value.startswith(base + ".")
    # Single * matches one segment only (no dots)
    if "*" in pattern:
        pat_parts = pattern.split(".")
        val_parts = value.split(".")
        if len(pat_parts) != len(val_parts):
            return False
        return all(fnmatch.fnmatch(v, p) for v, p in zip(val_parts, pat_parts, strict=True))
    return False


def _file_to_module(filepath: Path, root: Path) -> str:
    """Convert a file path to a dotted module path relative to root's parent.

    E.g. /project/cairn/core/search.py with root=/project/cairn
    → cairn.core.search
    """
    try:
        rel = filepath.relative_to(root.parent)
    except ValueError:
        return str(filepath)
    parts = list(rel.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _parse_rules(data: dict) -> tuple[list[BoundaryRule], list[IntegrationContract]]:
    """Parse boundaries and contracts from a config dict."""
    rules = []
    for item in data.get("boundaries", []):
        from_val = item.get("from", "")
        deny_val = item.get("deny", "")
        allow_val = item.get("allow", "")

        rules.append(BoundaryRule(
            name=item["name"],
            description=item.get("description", ""),
            from_patterns=_to_list(from_val),
            deny=_to_list(deny_val),
            allow_patterns=_to_list(allow_val),
        ))

    contracts = []
    for item in data.get("contracts", []):
        contracts.append(IntegrationContract(
            module=item["module"],
            exports=list(item.get("exports", [])),
        ))

    return rules, contracts


def load_config(config_path: Path) -> ArchConfig:
    """Load architecture rules from a YAML file."""
    with open(config_path) as f:
        data = yaml.safe_load(f)

    if not data or not isinstance(data, dict):
        return ArchConfig(source_path=config_path)

    rules, contracts = _parse_rules(data)
    return ArchConfig(boundaries=rules, contracts=contracts, source_path=config_path)


def load_config_from_string(yaml_content: str) -> ArchConfig:
    """Parse architecture rules from a YAML string (for project doc storage)."""
    data = yaml.safe_load(yaml_content)

    if not data or not isinstance(data, dict):
        return ArchConfig()

    rules, contracts = _parse_rules(data)
    return ArchConfig(boundaries=rules, contracts=contracts)


def _to_list(val: Any) -> list[str]:
    """Normalize a string or list to a list of strings."""
    if not val:
        return []
    if isinstance(val, str):
        return [val]
    return list(val)


def _check_contracts(
    config: ArchConfig,
    all_files: list[FileImports],
) -> list[ContractViolation]:
    """Evaluate integration contracts against file imports.

    For each contract, find ``from module import X`` where X is not in exports.
    """
    if not config.contracts:
        return []

    # Build lookup: module -> set of exported names
    contract_map: dict[str, set[str]] = {
        c.module: set(c.exports) for c in config.contracts
    }

    violations: list[ContractViolation] = []
    for fi in all_files:
        if fi.error:
            continue
        for imp in fi.imports:
            if not imp.is_from or not imp.names:
                continue
            exports = contract_map.get(imp.module)
            if exports is None:
                continue
            for name in imp.names:
                if name not in exports:
                    violations.append(ContractViolation(
                        rule_module=imp.module,
                        consumer_file=str(fi.path),
                        imported_name=name,
                        lineno=imp.lineno,
                    ))

    return violations


def check(config: ArchConfig, root: Path, exclude: set[str] | None = None) -> ArchReport:
    """Run architecture rules against all Python files under ``root``.

    Args:
        config: Loaded architecture rules.
        root: Source directory to scan (e.g. Path("cairn")).
        exclude: Directory names to skip.

    Returns:
        ArchReport with all violations found.
    """
    report = ArchReport()
    all_files = extract_imports_from_directory(root, exclude=exclude)
    report.files_checked = len(all_files)
    report.rules_evaluated = len(config.boundaries) + len(config.contracts)

    for fi in all_files:
        if fi.error:
            report.parse_errors.append(f"{fi.path}: {fi.error}")
            continue

        module_path = _file_to_module(fi.path, root)

        for rule in config.boundaries:
            if not rule.applies_to(module_path):
                continue
            if rule.is_allowed(module_path):
                continue

            for imp in fi.imports:
                if rule.is_denied(imp.module):
                    report.violations.append(Violation(
                        rule_name=rule.name,
                        file_path=fi.path,
                        imported_module=imp.module,
                        lineno=imp.lineno,
                        description=rule.description,
                    ))

    # Contract violations (source-only — needs name-level import info)
    report.contract_violations = _check_contracts(config, all_files)

    return report


def check_graph(
    config: ArchConfig,
    graph: GraphProvider,
    project_id: int,
) -> ArchReport:
    """Run architecture boundary rules against the Neo4j code graph.

    Uses IMPORTS edges between CodeFile nodes instead of re-parsing source.
    Contracts are skipped (they need name-level import info unavailable in the graph).

    Args:
        config: Loaded architecture rules.
        graph: Connected GraphProvider with code graph data.
        project_id: Numeric project ID in Postgres.

    Returns:
        ArchReport with boundary violations found.
    """
    from cairn.code.utils import path_to_module

    report = ArchReport()

    # Get all code files for this project
    code_files = graph.get_code_files(project_id)
    report.files_checked = len(code_files)
    report.rules_evaluated = len(config.boundaries)

    for cf in code_files:
        file_path = cf["path"]
        module_path = path_to_module(file_path)
        if not module_path:
            continue

        # Get files this file imports (IMPORTS edges)
        deps = graph.get_file_dependencies(file_path, project_id)

        for rule in config.boundaries:
            if not rule.applies_to(module_path):
                continue
            if rule.is_allowed(module_path):
                continue

            for dep in deps:
                dep_module = path_to_module(dep["path"])
                if not dep_module:
                    continue
                if rule.is_denied(dep_module):
                    report.violations.append(Violation(
                        rule_name=rule.name,
                        file_path=Path(file_path),
                        imported_module=dep_module,
                        lineno=0,  # line numbers unavailable in graph mode
                        description=rule.description,
                    ))

    return report
