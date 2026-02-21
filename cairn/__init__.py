"""Cairn: Semantic memory for AI agents."""

try:
    from importlib.metadata import version as _v
    __version__ = _v("cairn-mcp")
except Exception:
    from pathlib import Path as _P
    import re as _re
    _match = _re.search(r'version\s*=\s*"([^"]+)"', (_P(__file__).resolve().parent.parent / "pyproject.toml").read_text())
    __version__ = _match.group(1) if _match else "0.0.0"
