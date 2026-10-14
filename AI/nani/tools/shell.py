"""N.A.N.I. V2 — Structured Shell Execution Native Tool
Provides asynchronous command execution with process-group isolation,
timeout termination, output buffer limits, and working-directory boundary enforcement.
"""

import asyncio
import os
import signal
import time
from pathlib import Path
from typing import Any

from nani.core.task import RiskLevel, WorkerCapability
from nani.tools.filesystem import resolve_safe_path
from nani.tools.registry import BaseTool, ToolRegistry
from nani.tools.result import ToolResult

MAX_OUTPUT_CHARS = 100_000
DEFAULT_TIMEOUT_SECONDS = 30.0


class ShellTool(BaseTool):
    def __init__(
        self, workspace_path: Path | None = None, default_timeout: float = DEFAULT_TIMEOUT_SECONDS
    ) -> None:
        self.workspace_path = workspace_path
        self.default_timeout = default_timeout

    @property
    def name(self) -> str:
        return "shell"

    @property
    def description(self) -> str:
        return "Executes shell commands with timeout protection, process-group isolation, and workspace boundary checks."

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.MEDIUM

    @property
    def capability(self) -> WorkerCapability:
        return WorkerCapability.SYSTEM

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command line to execute"},
                "cmd": {"type": "string", "description": "Alternative alias for command"},
                "cwd": {
                    "type": "string",
                    "description": "Working directory path within authorized workspace",
                },
                "timeout": {
                    "type": "number",
                    "description": "Execution timeout in seconds",
                    "default": 30.0,
                },
                "workspace_path": {
                    "type": "string",
                    "description": "Optional workspace root override",
                },
            },
        }

    def _truncate_output(self, text: str) -> str:
        if len(text) > MAX_OUTPUT_CHARS:
            return (
                text[:MAX_OUTPUT_CHARS]
                + "\n[...OUTPUT TRUNCATED: EXCEEDED MAXIMUM BUFFER LIMIT...]"
            )
        return text

    async def run(self, **kwargs: Any) -> ToolResult:
        cmd = kwargs.get("command") or kwargs.get("cmd")
        if not cmd or not str(cmd).strip():
            return ToolResult.fail("Missing required parameter: 'command'")

        command_str = str(cmd).strip()
        ws = kwargs.get("workspace_path") or self.workspace_path
        cwd_param = kwargs.get("cwd") or "."

        try:
            safe_cwd = resolve_safe_path(cwd_param, ws)
            if not safe_cwd.is_dir():
                return ToolResult.fail(f"Working directory does not exist: {cwd_param}")
        except PermissionError as pe:
            return ToolResult.fail(str(pe))

        timeout = float(kwargs.get("timeout") or self.default_timeout)
        t_start = time.time()

        proc = None
        try:
            # Spawn process in its own process group (POSIX start_new_session)
            proc = await asyncio.create_subprocess_shell(
                command_str,
                cwd=str(safe_cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )

            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout,
            )
            duration_ms = int((time.time() - t_start) * 1000)

            stdout_str = self._truncate_output(stdout_bytes.decode("utf-8", errors="replace"))
            stderr_str = self._truncate_output(stderr_bytes.decode("utf-8", errors="replace"))
            exit_code = proc.returncode if proc.returncode is not None else 0

            if exit_code == 0:
                return ToolResult.ok(
                    stdout=stdout_str,
                    exit_code=exit_code,
                    duration_ms=duration_ms,
                    data={"command": command_str, "cwd": str(safe_cwd)},
                )
            else:
                return ToolResult.fail(
                    error=f"Command exited with non-zero code {exit_code}",
                    stderr=stderr_str,
                    exit_code=exit_code,
                    duration_ms=duration_ms,
                    metadata={"stdout": stdout_str, "command": command_str, "cwd": str(safe_cwd)},
                )

        except asyncio.TimeoutError:
            duration_ms = int((time.time() - t_start) * 1000)
            if proc and proc.pid:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
                try:
                    await asyncio.wait_for(proc.wait(), timeout=2.0)
                except Exception:
                    pass

            return ToolResult.fail(
                error=f"Command timed out after {timeout} seconds",
                exit_code=-1,
                duration_ms=duration_ms,
                metadata={"command": command_str, "timeout": True},
            )

        except Exception as e:
            duration_ms = int((time.time() - t_start) * 1000)
            return ToolResult.fail(
                error=f"Shell execution failure: {e}",
                duration_ms=duration_ms,
                metadata={"command": command_str},
            )


def register_shell_tools(registry: ToolRegistry, workspace_path: Path | None = None) -> None:
    """Registers shell tools under primary 'shell' and alias 'run_shell'."""
    tool = ShellTool(workspace_path)
    if registry.exists("shell"):
        registry.replace(tool)
    else:
        registry.register(tool)

    # Register alias run_shell
    class RunShellAlias(ShellTool):
        @property
        def name(self) -> str:
            return "run_shell"

    alias_tool = RunShellAlias(workspace_path)
    if registry.exists("run_shell"):
        registry.replace(alias_tool)
    else:
        registry.register(alias_tool)
