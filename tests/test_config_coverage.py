"""Tests to prevent ghost config flags and dead code regression.

Each capability flag in LLMCapabilities must be referenced in actual code
(not just config.py). This catches ghost flags — config entries with no
implementation behind them.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

from cairn.config import LLMCapabilities, EXPERIMENTAL_CAPABILITIES


# All capability flag names on LLMCapabilities (excluding methods)
CAPABILITY_FLAGS = {
    name for name, val in LLMCapabilities.__dataclass_fields__.items()
}

# Files that are "config infrastructure" — references here don't count
# as proving a flag has implementation code.
CONFIG_INFRA_FILES = {
    "cairn/config.py",
    "cairn-ui/src/app/settings/page.tsx",
}

# Root of the cairn package
CAIRN_ROOT = Path(__file__).parent.parent / "cairn"


def _find_references(flag_name: str) -> list[str]:
    """Find Python files that reference a capability flag name."""
    refs = []
    for root, dirs, files in os.walk(CAIRN_ROOT):
        # Skip __pycache__, node_modules, etc.
        dirs[:] = [d for d in dirs if d not in {"__pycache__", "node_modules", ".git"}]
        for fname in files:
            if not fname.endswith(".py"):
                continue
            fpath = os.path.join(root, fname)
            rel_path = os.path.relpath(fpath, CAIRN_ROOT.parent)
            if rel_path in CONFIG_INFRA_FILES:
                continue
            try:
                content = open(fpath).read()
                if flag_name in content:
                    refs.append(rel_path)
            except Exception:
                pass
    return refs


class TestCapabilityFlagCoverage:
    """Every capability flag must have implementation code."""

    @pytest.mark.parametrize("flag", sorted(CAPABILITY_FLAGS))
    def test_flag_has_implementation(self, flag):
        refs = _find_references(flag)
        assert refs, (
            f"Capability flag '{flag}' has no references outside config infrastructure. "
            f"This is a ghost flag — it exists in config but nothing uses it. "
            f"Either implement it or remove it."
        )

    def test_active_list_covers_all_bool_flags(self):
        """active_list() must mention every boolean capability flag."""
        # Get the source of active_list
        import inspect
        source = inspect.getsource(LLMCapabilities.active_list)

        bool_flags = {
            name for name, field in LLMCapabilities.__dataclass_fields__.items()
            if field.default in (True, False)
        }

        for flag in bool_flags:
            assert flag in source, (
                f"Boolean flag '{flag}' is not listed in active_list(). "
                f"It won't appear in capability reports."
            )

    def test_experimental_set_is_subset_of_flags(self):
        """EXPERIMENTAL_CAPABILITIES must only contain real flag names."""
        for name in EXPERIMENTAL_CAPABILITIES:
            assert name in CAPABILITY_FLAGS, (
                f"EXPERIMENTAL_CAPABILITIES contains '{name}' which is not "
                f"a field on LLMCapabilities"
            )
