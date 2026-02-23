"""CI-enforced architecture boundary tests for Cairn.

Runs the actual architecture rules from architecture.yaml against
Cairn's own source code. Fails if any boundary is violated.
"""

from pathlib import Path

from cairn.code.arch_rules import load_config, check


# Find repo root (where architecture.yaml lives)
REPO_ROOT = Path(__file__).parent.parent
CONFIG_PATH = REPO_ROOT / "architecture.yaml"
SOURCE_ROOT = REPO_ROOT / "cairn"


def test_architecture_yaml_exists():
    """architecture.yaml must exist at repo root."""
    assert CONFIG_PATH.exists(), f"Missing {CONFIG_PATH}"


def test_no_boundary_violations():
    """All architecture boundary rules must pass."""
    config = load_config(CONFIG_PATH)
    assert len(config.boundaries) > 0, "No rules defined in architecture.yaml"

    report = check(config, SOURCE_ROOT)

    if not report.clean:
        # Format a clear error message
        lines = [f"\n{len(report.violations)} architecture violation(s):\n"]
        for v in report.violations:
            rel_path = v.file_path.relative_to(REPO_ROOT) if v.file_path.is_relative_to(REPO_ROOT) else v.file_path
            lines.append(f"  [{v.rule_name}] {rel_path}:{v.lineno}")
            lines.append(f"    imports: {v.imported_module}")
            if v.description:
                lines.append(f"    rule: {v.description}")
            lines.append("")
        assert False, "\n".join(lines)


def test_no_parse_errors():
    """All Python files should parse without errors."""
    config = load_config(CONFIG_PATH)
    report = check(config, SOURCE_ROOT)

    if report.parse_errors:
        lines = [f"\n{len(report.parse_errors)} parse error(s):\n"]
        for err in report.parse_errors:
            lines.append(f"  {err}")
        assert False, "\n".join(lines)
