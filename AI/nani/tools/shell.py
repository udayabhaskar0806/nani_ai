"""N.A.N.I. V2 — Structured Shell Execution Native Tool
Provides supervised command execution with process-group isolation,
timeout termination, output buffer limits, and working-directory boundary enforcement.
"""

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

        # Execute through SubprocessSupervisor with enforceable isolation
        argv = ["/bin/sh", "-c", command_str]
        return await SubprocessSupervisor.run_supervised(
            argv=argv,
            cwd=safe_cwd,
            workspace=ws,
            timeout=timeout,
            task_id=task_id,
            isolated=self.isolated,
            network_allowed=False,
        )


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
