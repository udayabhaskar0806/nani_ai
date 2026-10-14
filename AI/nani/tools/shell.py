"""N.A.N.I. V2 — Structured Shell Execution Native Tool
Provides supervised command execution with process-group isolation,
timeout termination, output buffer limits, and working-directory boundary enforcement.
"""

import re
import tempfile
from pathlib import Path
from typing import Any

from nani.core.context import ExecutionContext
from nani.core.task import RiskLevel, WorkerCapability
from nani.tools.path_utils import resolve_safe_path
from nani.tools.registry import BaseTool, ToolRegistry
from nani.tools.result import ToolResult
from nani.tools.supervisor import SubprocessSupervisor

DEFAULT_TIMEOUT_SECONDS = 30.0


class ShellTool(BaseTool):
    def __init__(
        self,
        workspace_path: Path | None = None,
        default_timeout: float = DEFAULT_TIMEOUT_SECONDS,
        isolated: bool = True,
    ) -> None:
        self.workspace_path = workspace_path
        self.default_timeout = default_timeout
        self.isolated = isolated

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
            },
        }

    async def run(self, **kwargs: Any) -> ToolResult:
        context: ExecutionContext | None = kwargs.pop("context", None)
        cmd = kwargs.get("command") or kwargs.get("cmd")
        if not cmd or not str(cmd).strip():
            return ToolResult.fail("Missing required parameter: 'command'")

        command_str = str(cmd).strip()

        # Workspace determined strictly from trusted context
        if context and context.workspace:
            ws = context.workspace
        elif self.workspace_path:
            ws = self.workspace_path.resolve()
        else:
            ws = Path.cwd().resolve()

        cwd_param = kwargs.get("cwd") or "."

        try:
            safe_cwd = resolve_safe_path(cwd_param, ws)
            if not safe_cwd.is_dir():
                return ToolResult.fail(f"Working directory does not exist: {cwd_param}")
        except PermissionError as pe:
            return ToolResult.fail(str(pe))

        timeout = float(kwargs.get("timeout") or self.default_timeout)
        task_id = context.task_id if context else None
        allow_unsandboxed = bool(context and context.metadata.get("allow_unsandboxed", False))

        stdin_param = kwargs.get("stdin")
        if not stdin_param and context and context.metadata:
            stdin_param = context.metadata.get("stdin")

        stdin_bytes = (
            stdin_param.encode()
            if isinstance(stdin_param, str)
            else stdin_param
            if isinstance(stdin_param, bytes)
            else None
        )

        from nani.core.sudo import SudoManager

        sudo_pwd = (
            kwargs.get("sudo_password")
            or (context.metadata.get("sudo_password") if context and context.metadata else None)
            or SudoManager.get_session_password()
        )

        askpass_path: Path | None = None
        custom_env: dict[str, str] = {}
        if sudo_pwd and re.search(r"\bsudo\b", command_str):
            allow_unsandboxed = True
            with tempfile.NamedTemporaryFile(mode="w", delete=False, prefix="nani_askpass_") as tf:
                tf.write(f"#!/bin/sh\nexec cat << 'NANI_EOF'\n{sudo_pwd}\nNANI_EOF\n")
                askpass_path = Path(tf.name)
            askpass_path.chmod(0o700)
            custom_env["SUDO_ASKPASS"] = str(askpass_path)
            command_str = re.sub(r"\bsudo\b(?!\s+-[AS])", "sudo -A", command_str)

        try:
            # Execute through SubprocessSupervisor with enforceable isolation
            argv = ["/bin/sh", "-c", command_str]
            return await SubprocessSupervisor.run_supervised(
                argv=argv,
                cwd=safe_cwd,
                workspace=ws,
                timeout=timeout,
                env=custom_env or None,
                task_id=task_id,
                isolated=self.isolated,
                network_allowed=False,
                allow_unsandboxed=allow_unsandboxed,
                stdin_data=stdin_bytes,
            )
        finally:
            if askpass_path and askpass_path.exists():
                try:
                    askpass_path.unlink()
                except Exception:
                    pass


def register_shell_tools(registry: ToolRegistry, workspace_path: Path | None = None) -> None:
    """Registers shell tools under primary 'shell' and alias 'run_shell'."""
    tool = ShellTool(workspace_path)
    if registry.exists("shell"):
        registry.replace(tool)
    else:
        registry.register(tool)

    class RunShellAlias(ShellTool):
        @property
        def name(self) -> str:
            return "run_shell"

    alias_tool = RunShellAlias(workspace_path)
    if registry.exists("run_shell"):
        registry.replace(alias_tool)
    else:
        registry.register(alias_tool)
