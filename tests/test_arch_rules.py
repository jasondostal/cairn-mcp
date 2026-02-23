"""Unit tests for the architecture rule engine."""

from pathlib import Path
from unittest.mock import MagicMock

from cairn.code.imports import ImportInfo, FileImports, extract_imports
from cairn.code.arch_rules import (
    ArchConfig, BoundaryRule, Violation, ArchReport,
    IntegrationContract, ContractViolation,
    _match, _file_to_module, load_config, load_config_from_string,
    check, check_graph,
)
from cairn.code.utils import path_to_module


# ── Pattern matching ──────────────────────────────────────────


class TestMatch:

    def test_exact(self):
        assert _match("cairn.server", "cairn.server")

    def test_exact_no_match(self):
        assert not _match("cairn.server", "cairn.core")

    def test_star_matches_one_level(self):
        assert _match("cairn.core.search", "cairn.core.*")

    def test_star_no_deep_match(self):
        assert not _match("cairn.core.sub.mod", "cairn.core.*")

    def test_doublestar_matches_self(self):
        assert _match("cairn.core", "cairn.core.**")

    def test_doublestar_matches_child(self):
        assert _match("cairn.core.search", "cairn.core.**")

    def test_doublestar_matches_deep(self):
        assert _match("cairn.core.sub.deep.mod", "cairn.core.**")

    def test_doublestar_no_partial(self):
        assert not _match("cairn.corefoo", "cairn.core.**")

    def test_no_match(self):
        assert not _match("neo4j", "cairn.**")


# ── File to module conversion ─────────────────────────────────


class TestFileToModule:

    def test_regular_file(self):
        result = _file_to_module(
            Path("/project/cairn/core/search.py"),
            Path("/project/cairn"),
        )
        assert result == "cairn.core.search"

    def test_init_file(self):
        result = _file_to_module(
            Path("/project/cairn/core/__init__.py"),
            Path("/project/cairn"),
        )
        assert result == "cairn.core"

    def test_top_level(self):
        result = _file_to_module(
            Path("/project/cairn/server.py"),
            Path("/project/cairn"),
        )
        assert result == "cairn.server"


# ── path_to_module (shared util) ─────────────────────────────


class TestPathToModule:

    def test_regular_file(self):
        assert path_to_module("cairn/core/search.py") == "cairn.core.search"

    def test_init_file(self):
        assert path_to_module("cairn/core/__init__.py") == "cairn.core"

    def test_non_python(self):
        assert path_to_module("cairn/core/README.md") is None

    def test_top_level(self):
        assert path_to_module("setup.py") == "setup"


# ── Import extraction ─────────────────────────────────────────


class TestExtractImports:

    def test_import_statement(self):
        result = extract_imports("import os\nimport cairn.core.services\n")
        assert len(result.imports) == 2
        assert result.imports[0].module == "os"
        assert result.imports[1].module == "cairn.core.services"

    def test_from_import(self):
        result = extract_imports("from cairn.core.services import Services\n")
        assert len(result.imports) == 1
        imp = result.imports[0]
        assert imp.module == "cairn.core.services"
        assert imp.names == ("Services",)
        assert imp.is_from

    def test_syntax_error(self):
        result = extract_imports("def broken(:\n")
        assert result.error is not None
        assert len(result.imports) == 0

    def test_module_paths_deduped(self):
        result = extract_imports(
            "from cairn.core import A\nfrom cairn.core import B\nimport cairn.server\n"
        )
        assert result.module_paths == ["cairn.core", "cairn.server"]


# ── BoundaryRule logic ────────────────────────────────────────


class TestBoundaryRule:

    def test_applies_to_all_when_no_from(self):
        rule = BoundaryRule(name="r", deny=["neo4j"], from_patterns=[], allow_patterns=[])
        assert rule.applies_to("anything.at.all")

    def test_applies_to_matching_from(self):
        rule = BoundaryRule(name="r", deny=["x"], from_patterns=["cairn.core.**"], allow_patterns=[])
        assert rule.applies_to("cairn.core.search")
        assert not rule.applies_to("cairn.api.routes")

    def test_allow_exempts(self):
        rule = BoundaryRule(name="r", deny=["x"], from_patterns=[], allow_patterns=["cairn.graph.**"])
        assert rule.is_allowed("cairn.graph.neo4j_provider")
        assert not rule.is_allowed("cairn.core.services")

    def test_deny_matches(self):
        rule = BoundaryRule(name="r", deny=["cairn.server", "cairn.api.**"], from_patterns=[], allow_patterns=[])
        assert rule.is_denied("cairn.server")
        assert rule.is_denied("cairn.api.routes")
        assert not rule.is_denied("cairn.core.services")


# ── End-to-end check ──────────────────────────────────────────


class TestCheck:

    def test_detects_violation(self, tmp_path):
        # Create a file that violates a rule
        src = tmp_path / "pkg"
        src.mkdir()
        (src / "__init__.py").write_text("")
        core = src / "core"
        core.mkdir()
        (core / "__init__.py").write_text("")
        (core / "bad.py").write_text("import pkg.server\n")
        (src / "server.py").write_text("# server\n")

        config = ArchConfig(boundaries=[
            BoundaryRule(
                name="core-no-server",
                deny=["pkg.server"],
                from_patterns=["pkg.core.**"],
                allow_patterns=[],
            ),
        ])

        report = check(config, src)
        assert not report.clean
        assert len(report.violations) == 1
        v = report.violations[0]
        assert v.rule_name == "core-no-server"
        assert v.imported_module == "pkg.server"

    def test_allow_exemption(self, tmp_path):
        src = tmp_path / "pkg"
        src.mkdir()
        (src / "__init__.py").write_text("")
        api = src / "api"
        api.mkdir()
        (api / "__init__.py").write_text("")
        # This file is allowed by exception
        (api / "core.py").write_text("from pkg.storage import settings\n")
        storage = src / "storage"
        storage.mkdir()
        (storage / "__init__.py").write_text("")
        (storage / "settings.py").write_text("")

        config = ArchConfig(boundaries=[
            BoundaryRule(
                name="no-direct-storage",
                deny=["pkg.storage.**"],
                from_patterns=["pkg.api.**"],
                allow_patterns=["pkg.api.core"],
            ),
        ])

        report = check(config, src)
        assert report.clean

    def test_clean_codebase(self, tmp_path):
        src = tmp_path / "pkg"
        src.mkdir()
        (src / "__init__.py").write_text("")
        (src / "main.py").write_text("import os\nimport sys\n")

        config = ArchConfig(boundaries=[
            BoundaryRule(name="no-evil", deny=["evil"], from_patterns=[], allow_patterns=[]),
        ])

        report = check(config, src)
        assert report.clean
        assert report.files_checked == 2  # __init__.py + main.py


# ── YAML loading ──────────────────────────────────────────────


class TestLoadConfig:

    def test_load_yaml(self, tmp_path):
        cfg_file = tmp_path / "arch.yaml"
        cfg_file.write_text("""
boundaries:
  - name: test-rule
    description: Test
    from: "pkg.core.**"
    deny: "pkg.server"
    allow: "pkg.core.special"
""")
        config = load_config(cfg_file)
        assert len(config.boundaries) == 1
        rule = config.boundaries[0]
        assert rule.name == "test-rule"
        assert rule.from_patterns == ["pkg.core.**"]
        assert rule.deny == ["pkg.server"]
        assert rule.allow_patterns == ["pkg.core.special"]

    def test_load_multiple_deny(self, tmp_path):
        cfg_file = tmp_path / "arch.yaml"
        cfg_file.write_text("""
boundaries:
  - name: multi
    deny:
      - "evil"
      - "bad"
""")
        config = load_config(cfg_file)
        assert config.boundaries[0].deny == ["evil", "bad"]

    def test_load_empty(self, tmp_path):
        cfg_file = tmp_path / "arch.yaml"
        cfg_file.write_text("")
        config = load_config(cfg_file)
        assert len(config.boundaries) == 0

    def test_load_with_contracts(self, tmp_path):
        cfg_file = tmp_path / "arch.yaml"
        cfg_file.write_text("""
boundaries:
  - name: test-rule
    deny: "evil"

contracts:
  - module: "pkg.core.services"
    exports: ["ServiceContainer", "get_services"]
  - module: "pkg.graph.interface"
    exports: ["GraphProvider"]
""")
        config = load_config(cfg_file)
        assert len(config.boundaries) == 1
        assert len(config.contracts) == 2
        assert config.contracts[0].module == "pkg.core.services"
        assert config.contracts[0].exports == ["ServiceContainer", "get_services"]
        assert config.contracts[1].module == "pkg.graph.interface"
        assert config.contracts[1].exports == ["GraphProvider"]


# ── load_config_from_string ───────────────────────────────────


class TestLoadConfigFromString:

    def test_basic(self):
        yaml_str = """
boundaries:
  - name: core-no-server
    from: "pkg.core.**"
    deny: "pkg.server"
"""
        config = load_config_from_string(yaml_str)
        assert len(config.boundaries) == 1
        assert config.boundaries[0].name == "core-no-server"
        assert config.source_path is None

    def test_with_contracts(self):
        yaml_str = """
boundaries:
  - name: test
    deny: "evil"

contracts:
  - module: "pkg.api"
    exports: ["create_app"]
"""
        config = load_config_from_string(yaml_str)
        assert len(config.boundaries) == 1
        assert len(config.contracts) == 1
        assert config.contracts[0].module == "pkg.api"
        assert config.contracts[0].exports == ["create_app"]

    def test_empty_string(self):
        config = load_config_from_string("")
        assert len(config.boundaries) == 0
        assert len(config.contracts) == 0

    def test_boundaries_only(self):
        yaml_str = """
boundaries:
  - name: rule1
    deny: "bad"
"""
        config = load_config_from_string(yaml_str)
        assert len(config.boundaries) == 1
        assert len(config.contracts) == 0


# ── Integration contracts ─────────────────────────────────────


class TestContracts:

    def test_contract_violation_detected(self, tmp_path):
        """Importing an undeclared name triggers a contract violation."""
        src = tmp_path / "pkg"
        src.mkdir()
        (src / "__init__.py").write_text("")
        (src / "api.py").write_text("def create_app(): pass\ndef _internal(): pass\n")
        (src / "consumer.py").write_text("from pkg.api import create_app, _internal\n")

        config = ArchConfig(
            contracts=[
                IntegrationContract(module="pkg.api", exports=["create_app"]),
            ],
        )

        report = check(config, src)
        assert not report.clean
        assert len(report.contract_violations) == 1
        cv = report.contract_violations[0]
        assert cv.rule_module == "pkg.api"
        assert cv.imported_name == "_internal"
        assert "consumer.py" in cv.consumer_file

    def test_contract_clean(self, tmp_path):
        """Importing only declared names is clean."""
        src = tmp_path / "pkg"
        src.mkdir()
        (src / "__init__.py").write_text("")
        (src / "api.py").write_text("def create_app(): pass\n")
        (src / "consumer.py").write_text("from pkg.api import create_app\n")

        config = ArchConfig(
            contracts=[
                IntegrationContract(module="pkg.api", exports=["create_app"]),
            ],
        )

        report = check(config, src)
        assert report.clean

    def test_contract_ignores_non_from_imports(self, tmp_path):
        """Plain 'import X' doesn't trigger contract checks (no name-level info)."""
        src = tmp_path / "pkg"
        src.mkdir()
        (src / "__init__.py").write_text("")
        (src / "consumer.py").write_text("import pkg.api\n")

        config = ArchConfig(
            contracts=[
                IntegrationContract(module="pkg.api", exports=["create_app"]),
            ],
        )

        report = check(config, src)
        assert report.clean

    def test_contract_ignores_unrelated_modules(self, tmp_path):
        """Imports from modules without contracts are ignored."""
        src = tmp_path / "pkg"
        src.mkdir()
        (src / "__init__.py").write_text("")
        (src / "consumer.py").write_text("from os.path import join\n")

        config = ArchConfig(
            contracts=[
                IntegrationContract(module="pkg.api", exports=["create_app"]),
            ],
        )

        report = check(config, src)
        assert report.clean

    def test_rules_evaluated_includes_contracts(self, tmp_path):
        """rules_evaluated counts both boundary rules and contracts."""
        src = tmp_path / "pkg"
        src.mkdir()
        (src / "__init__.py").write_text("")
        (src / "main.py").write_text("import os\n")

        config = ArchConfig(
            boundaries=[
                BoundaryRule(name="r", deny=["evil"], from_patterns=[], allow_patterns=[]),
            ],
            contracts=[
                IntegrationContract(module="pkg.api", exports=["create_app"]),
            ],
        )

        report = check(config, src)
        assert report.rules_evaluated == 2  # 1 boundary + 1 contract


# ── check_graph ───────────────────────────────────────────────


class TestCheckGraph:

    def _make_graph(self, files, dependencies):
        """Create a mock GraphProvider with given files and dependency edges.

        Args:
            files: list of {"path": str, "language": str, ...}
            dependencies: dict mapping file_path -> list of {"path": str, ...}
        """
        graph = MagicMock()
        graph.get_code_files.return_value = files
        graph.get_file_dependencies.side_effect = lambda path, pid: dependencies.get(path, [])
        return graph

    def test_detects_violation(self):
        graph = self._make_graph(
            files=[
                {"path": "pkg/core/bad.py", "language": "python"},
                {"path": "pkg/server.py", "language": "python"},
            ],
            dependencies={
                "pkg/core/bad.py": [{"path": "pkg/server.py", "language": "python"}],
                "pkg/server.py": [],
            },
        )

        config = ArchConfig(boundaries=[
            BoundaryRule(
                name="core-no-server",
                deny=["pkg.server"],
                from_patterns=["pkg.core.**"],
                allow_patterns=[],
            ),
        ])

        report = check_graph(config, graph, project_id=1)
        assert not report.clean
        assert len(report.violations) == 1
        v = report.violations[0]
        assert v.rule_name == "core-no-server"
        assert v.imported_module == "pkg.server"
        assert v.lineno == 0  # no line numbers in graph mode

    def test_clean(self):
        graph = self._make_graph(
            files=[
                {"path": "pkg/core/search.py", "language": "python"},
                {"path": "pkg/core/utils.py", "language": "python"},
            ],
            dependencies={
                "pkg/core/search.py": [{"path": "pkg/core/utils.py", "language": "python"}],
                "pkg/core/utils.py": [],
            },
        )

        config = ArchConfig(boundaries=[
            BoundaryRule(
                name="core-no-server",
                deny=["pkg.server"],
                from_patterns=["pkg.core.**"],
                allow_patterns=[],
            ),
        ])

        report = check_graph(config, graph, project_id=1)
        assert report.clean
        assert report.files_checked == 2

    def test_allow_exemption(self):
        graph = self._make_graph(
            files=[
                {"path": "pkg/graph/provider.py", "language": "python"},
            ],
            dependencies={
                "pkg/graph/provider.py": [{"path": "pkg/external/neo4j.py", "language": "python"}],
            },
        )

        config = ArchConfig(boundaries=[
            BoundaryRule(
                name="no-external",
                deny=["pkg.external.**"],
                from_patterns=[],
                allow_patterns=["pkg.graph.**"],
            ),
        ])

        report = check_graph(config, graph, project_id=1)
        assert report.clean

    def test_skips_contracts(self):
        """check_graph does not evaluate contracts (graph lacks name-level info)."""
        graph = self._make_graph(
            files=[{"path": "pkg/main.py", "language": "python"}],
            dependencies={"pkg/main.py": []},
        )

        config = ArchConfig(
            contracts=[
                IntegrationContract(module="pkg.api", exports=["create_app"]),
            ],
        )

        report = check_graph(config, graph, project_id=1)
        assert report.clean
        assert len(report.contract_violations) == 0


# ── ArchReport ────────────────────────────────────────────────


class TestArchReport:

    def test_summary_with_contracts(self):
        report = ArchReport(
            violations=[
                Violation(
                    rule_name="r1",
                    file_path=Path("a.py"),
                    imported_module="bad",
                    lineno=5,
                ),
            ],
            contract_violations=[
                ContractViolation(
                    rule_module="pkg.api",
                    consumer_file="consumer.py",
                    imported_name="_secret",
                    lineno=10,
                ),
            ],
            files_checked=3,
            rules_evaluated=2,
        )
        assert not report.clean
        s = report.summary()
        assert "2 violation(s)" in s
        assert "[r1]" in s
        assert "[contract:pkg.api]" in s
        assert "_secret" in s
