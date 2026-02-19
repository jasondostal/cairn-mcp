"""Claude Code CLI backend — spawns ``claude -p`` as subprocess.

Uses the Claude Code CLI (``claude``) in non-interactive mode to run
autonomous agent sessions. Each ``send_message`` call invokes a fresh
``claude -p`` subprocess; session continuity is maintained via
``--resume <session_id>`` once the first response captures Claude's
real session ID from JSON output.
"""

from __future__ import annotations

import json
import logging
import shlex
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cairn.integrations.interface import (
    AgentInfo,
    AgentMessage,
    AgentSession,
    BackendHealth,
    WorkspaceBackend,
    WorkspaceBackendError,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class ClaudeCodeConfig:
    """Configuration for the Claude Code backend."""
    working_dir: str = ""               # cwd for claude subprocess
    max_turns: int = 25                 # --max-turns
    max_budget_usd: float = 10.0        # --max-budget-usd (0 = no limit)
    cairn_mcp_url: str = ""             # Cairn MCP URL for self-service context
    default_risk_tier: int = 0          # default risk tier for new sessions
    ssh_host: str = ""                  # Remote host (empty = local execution)
    ssh_user: str = ""                  # SSH user (empty = current user)
    ssh_key_path: str = ""              # Path to SSH private key (empty = default)


# ---------------------------------------------------------------------------
# Risk tier → permission mapping
# ---------------------------------------------------------------------------

# Maps risk tier to CLI permission args.
# Tier 0: full autonomy
# Tier 1: broad tool access (Read, Edit, Write, Bash, Glob, Grep + Cairn MCP)
# Tier 2: read-heavy, no edit/write
# Tier 3: research-only (Read, Glob, Grep + Cairn MCP)

_TIER_PERMISSIONS: dict[int, list[str]] = {
    0: ["--dangerously-skip-permissions"],
    1: ["--allowedTools", "Read,Edit,Write,Bash,Glob,Grep,Task,WebFetch,WebSearch,mcp__cairn__orient,mcp__cairn__search,mcp__cairn__recall,mcp__cairn__store,mcp__cairn__rules,mcp__cairn__work_items"],
    2: ["--allowedTools", "Read,Bash,Glob,Grep,Task,WebFetch,WebSearch,mcp__cairn__orient,mcp__cairn__search,mcp__cairn__recall,mcp__cairn__store,mcp__cairn__rules,mcp__cairn__work_items"],
    3: ["--allowedTools", "Read,Glob,Grep,WebFetch,WebSearch,mcp__cairn__orient,mcp__cairn__search,mcp__cairn__recall,mcp__cairn__rules"],
}


# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------


class ClaudeCodeBackend(WorkspaceBackend):
    """Workspace backend that spawns ``claude -p`` subprocesses.

    Sessions are tracked locally — create_session generates a placeholder
    ID, and the real Claude session_id is captured from JSON output on
    the first message exchange.
    """

    def __init__(self, config: ClaudeCodeConfig | None = None):
        self._config = config or ClaudeCodeConfig()
        # Local session store: placeholder_id → session metadata
        self._sessions: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    # -- Core ----------------------------------------------------------------

    def backend_name(self) -> str:
        return "claude_code"

    def is_healthy(self) -> bool:
        try:
            result = self._run_cmd(["claude", "--version"], timeout=10)
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return False

    def health(self) -> BackendHealth:
        try:
            result = self._run_cmd(["claude", "--version"], timeout=10)
            if result.returncode != 0:
                return BackendHealth(healthy=False, extra={
                    "error": result.stderr.strip() or "claude CLI exited non-zero",
                    "mode": "ssh" if self._config.ssh_host else "local",
                })
            version = result.stdout.strip() or result.stderr.strip()
            return BackendHealth(healthy=True, version=version, extra={
                "mode": "ssh" if self._config.ssh_host else "local",
                "ssh_host": self._config.ssh_host or None,
            })
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            return BackendHealth(healthy=False, extra={
                "error": str(exc),
                "mode": "ssh" if self._config.ssh_host else "local",
            })

    def create_session(self, *, title: str | None = None, parent_id: str | None = None) -> AgentSession:
        session_id = f"cc-{int(time.time() * 1000)}"
        session = AgentSession(
            id=session_id,
            title=title,
            created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        with self._lock:
            self._sessions[session_id] = {
                "session": session,
                "claude_session_id": None,  # captured from first response
                "risk_tier": self._config.default_risk_tier,
                "model": None,  # set on first send_message if provided
            }
        return session

    def send_message(
        self,
        session_id: str,
        text: str,
        *,
        agent: str | None = None,
        risk_tier: int | None = None,
        model: str | None = None,
        **kwargs: Any,
    ) -> AgentMessage:
        with self._lock:
            meta = self._sessions.get(session_id)
        if not meta:
            raise WorkspaceBackendError(
                f"Session {session_id} not found",
                backend="claude_code",
            )

        tier = risk_tier if risk_tier is not None else meta.get("risk_tier", self._config.default_risk_tier)
        claude_sid = meta.get("claude_session_id")
        resolved_model = model or meta.get("model")

        # Persist model choice on session for future --resume calls
        if resolved_model and not meta.get("model"):
            with self._lock:
                meta["model"] = resolved_model

        args = self._build_cli_args(text, risk_tier=tier, claude_session_id=claude_sid, model=resolved_model)

        try:
            result = self._run_cmd(args, timeout=600)
        except subprocess.TimeoutExpired:
            raise WorkspaceBackendError(
                f"Claude CLI timed out after 600s for session {session_id}",
                backend="claude_code",
            )
        except FileNotFoundError:
            raise WorkspaceBackendError(
                "claude CLI not found — is Claude Code installed?",
                backend="claude_code",
            )

        if result.returncode != 0 and not result.stdout.strip():
            raise WorkspaceBackendError(
                f"Claude CLI exited with code {result.returncode}: {result.stderr[:500]}",
                backend="claude_code",
            )

        return self._parse_response(session_id, result.stdout)

    def send_message_async(
        self,
        session_id: str,
        text: str,
        *,
        agent: str | None = None,
        risk_tier: int | None = None,
        model: str | None = None,
        **kwargs: Any,
    ) -> None:
        def _run():
            try:
                self.send_message(session_id, text, agent=agent, risk_tier=risk_tier, model=model, **kwargs)
            except WorkspaceBackendError:
                logger.warning("Async send_message failed for session %s", session_id, exc_info=True)

        thread = threading.Thread(target=_run, daemon=True, name=f"claude-code-{session_id}")
        thread.start()

    # -- Optional ------------------------------------------------------------

    def get_session(self, session_id: str) -> AgentSession:
        with self._lock:
            meta = self._sessions.get(session_id)
        if not meta:
            raise WorkspaceBackendError(f"Session {session_id} not found", backend="claude_code")
        return meta["session"]

    def delete_session(self, session_id: str) -> bool:
        with self._lock:
            removed = self._sessions.pop(session_id, None)
        return removed is not None

    def abort_session(self, session_id: str) -> bool:
        # Claude Code CLI runs synchronously per call — there's no long-running
        # process to abort. Return True as a no-op acknowledgement.
        return True

    def list_agents(self) -> list[AgentInfo]:
        return [
            AgentInfo(
                id="claude-code-opus",
                name="Claude Code (Opus)",
                description="Claude Code CLI — Opus 4.6",
                model="claude-opus-4-6",
                backend="claude_code",
            ),
            AgentInfo(
                id="claude-code-sonnet",
                name="Claude Code (Sonnet)",
                description="Claude Code CLI — Sonnet 4.6",
                model="claude-sonnet-4-6",
                backend="claude_code",
            ),
        ]

    # -- Capabilities --------------------------------------------------------

    def supports_fork(self) -> bool:
        return False

    def supports_diff(self) -> bool:
        return False

    def supports_abort(self) -> bool:
        return True  # no-op but acknowledged

    def supports_agents(self) -> bool:
        return True

    # -- Internal ------------------------------------------------------------

    def _run_cmd(
        self,
        args: list[str],
        *,
        timeout: int = 600,
    ) -> subprocess.CompletedProcess:
        """Execute a command locally or via SSH.

        When ``ssh_host`` is configured, wraps the command in an SSH call.
        MCP config is written as a remote temp file inline in the SSH command.
        """
        if not self._config.ssh_host:
            # Local execution
            cwd = self._config.working_dir or None
            return subprocess.run(
                args, capture_output=True, text=True, cwd=cwd, timeout=timeout,
            )

        # SSH execution — build remote command string
        ssh_target = self._config.ssh_host
        if self._config.ssh_user:
            ssh_target = f"{self._config.ssh_user}@{self._config.ssh_host}"

        # Rewrite --mcp-config to use a remote temp file
        remote_args = list(args)
        mcp_preamble = ""
        for i, arg in enumerate(remote_args):
            if arg == "--mcp-config" and i + 1 < len(remote_args):
                local_path = remote_args[i + 1]
                # Read the local temp file content and write it remotely
                try:
                    mcp_content = Path(local_path).read_text()
                    remote_path = f"/tmp/cairn-mcp-{int(time.time() * 1000)}.json"
                    mcp_preamble = f"cat > {remote_path} << 'MCPEOF'\n{mcp_content}\nMCPEOF\n"
                    remote_args[i + 1] = remote_path
                except OSError:
                    pass
                break

        # Build the remote shell command.
        # Source .profile so ~/.local/bin (Claude CLI) is on PATH for non-interactive SSH.
        remote_shell_cmd = shlex.join(remote_args)
        if self._config.working_dir:
            remote_shell_cmd = f"cd {shlex.quote(self._config.working_dir)} && {remote_shell_cmd}"
        if mcp_preamble:
            remote_shell_cmd = mcp_preamble + remote_shell_cmd
        remote_shell_cmd = f"source ~/.profile 2>/dev/null; {remote_shell_cmd}"

        ssh_args = [
            "ssh",
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=10",
        ]
        if self._config.ssh_key_path:
            ssh_args.extend(["-i", self._config.ssh_key_path])
            # Use known_hosts from same directory as the key if it exists
            known_hosts = Path(self._config.ssh_key_path).parent / "known_hosts"
            if known_hosts.exists():
                ssh_args.extend(["-o", f"UserKnownHostsFile={known_hosts}"])
        ssh_args.extend([ssh_target, remote_shell_cmd])

        return subprocess.run(
            ssh_args, capture_output=True, text=True, timeout=timeout,
        )

    def _build_cli_args(
        self,
        prompt: str,
        *,
        risk_tier: int = 0,
        claude_session_id: str | None = None,
        model: str | None = None,
    ) -> list[str]:
        """Build the ``claude`` CLI argument list."""
        args = [
            "claude", "-p", prompt,
            "--output-format", "json",
        ]

        # Model override (e.g. "claude-sonnet-4-6" to save Opus budget)
        if model:
            args.extend(["--model", model])

        if self._config.max_turns > 0:
            args.extend(["--max-turns", str(self._config.max_turns)])

        if self._config.max_budget_usd > 0:
            # Use string to avoid float formatting issues
            args.extend(["--max-budget-usd", f"{self._config.max_budget_usd:.2f}"])

        # MCP config for Cairn self-service
        mcp_config_path = self._generate_mcp_config()
        if mcp_config_path:
            args.extend(["--mcp-config", mcp_config_path])

        # Permission tier
        tier_args = _TIER_PERMISSIONS.get(risk_tier, _TIER_PERMISSIONS[0])
        args.extend(tier_args)

        # Session resumption
        if claude_session_id:
            args.extend(["--resume", claude_session_id])

        return args

    def _generate_mcp_config(self) -> str | None:
        """Generate a temp MCP config file pointing at Cairn's MCP endpoint.

        Returns the path to the temp file, or None if no MCP URL is configured.
        """
        if not self._config.cairn_mcp_url:
            return None

        # Use "type": "http" — matches the proven mcp.json config (see memory #98).
        # "type": "url" silently fails in Claude CLI ≤2.1.47.
        config = {
            "mcpServers": {
                "cairn": {
                    "type": "http",
                    "url": self._config.cairn_mcp_url,
                },
            },
        }

        # Use a persistent temp file (not deleted on close) — Claude CLI needs to read it.
        # These are tiny JSON files; OS will clean up /tmp on reboot.
        fd = tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            prefix="cairn-mcp-",
            delete=False,
        )
        json.dump(config, fd)
        fd.close()
        return fd.name

    def _parse_response(self, session_id: str, stdout: str) -> AgentMessage:
        """Parse Claude CLI JSON output into an AgentMessage.

        Claude CLI ``--output-format json`` emits a JSON object with fields:
        - result: the text response
        - session_id: Claude's internal session ID
        - cost_usd: total cost
        - duration_ms, num_turns, etc.
        """
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            # If not valid JSON, treat raw stdout as plain text response
            return AgentMessage(
                id=f"msg-{int(time.time() * 1000)}",
                role="assistant",
                parts=[{"type": "text", "text": stdout.strip()}],
                session_id=session_id,
            )

        # Capture Claude's real session ID for future resumption
        claude_sid = data.get("session_id")
        if claude_sid:
            with self._lock:
                meta = self._sessions.get(session_id)
                if meta:
                    meta["claude_session_id"] = claude_sid

        result_text = data.get("result", "")
        cost = data.get("cost_usd")

        return AgentMessage(
            id=f"msg-{int(time.time() * 1000)}",
            role="assistant",
            parts=[{"type": "text", "text": result_text}],
            session_id=session_id,
            cost_usd=cost,
            extra={
                k: v for k, v in data.items()
                if k not in ("result", "session_id", "cost_usd")
            },
        )

    def set_risk_tier(self, session_id: str, risk_tier: int) -> None:
        """Update the risk tier for an existing session."""
        with self._lock:
            meta = self._sessions.get(session_id)
            if meta:
                meta["risk_tier"] = risk_tier
