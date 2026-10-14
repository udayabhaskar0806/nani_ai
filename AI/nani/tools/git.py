"""N.A.N.I. V2 — Structured Git Inspection Native Tool
Provides read-only local Git repository inspection (status, diff, log, branch, show, rev_parse).
Strictly blocks destructive or remote operations (push, reset --hard, remote delete).
"""

import asyncio
from pathlib import Path
from typing import Any

from nani.core.task import RiskLevel, WorkerCapability
from nani.tools.filesystem import resolve_safe_path
from nani.tools.registry import BaseTool, ToolRegistry
from nani.tools.result import ToolResult

ALLOWED_GIT_OPERATIONS = {
    "status": ["status", "--short"],
    "diff": ["diff"],
    "log": ["log", "-n", "10", "--oneline"],
    "branch": ["branch", "-a"],
    "show": ["show", "--stat"],
    "rev_parse": ["rev-parse", "HEAD"],
}

FORBIDDEN_PATTERNS = ["push", "reset", "clean", "checkout -f", "rm", "branch -d", "branch -D"]


class GitTool(BaseTool):
    def __init__(self, workspace_path: Path | None = None) -> None:
        self.workspace_path = workspace_path

    @property
    def name(self) -> str:
        return "git"

    @property
    def description(self) -> str:
        return "Performs safe local read-only Git repository inspection (status, diff, log, branch, show, rev_parse)."

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.LOW

    @property
    def capability(self) -> WorkerCapability:
        return WorkerCapability.CODING

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["status", "diff", "log", "branch", "show", "rev_parse"],
                },
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional flags or targets (e.g. ['HEAD~1'], ['main'])",
                },
                "cwd": {"type": "string", "description": "Repository directory within workspace"},
                "workspace_path": {
                    "type": "string",
                    "description": "Optional workspace root override",
                },
            },
            "required": ["operation"],
        }

    async def run(self, **kwargs: Any) -> ToolResult:
        operation = kwargs.get("operation")
        if not operation:
            return ToolResult.fail("Missing required parameter: 'operation'")

        op_name = str(operation).strip().lower()
        if op_name not in ALLOWED_GIT_OPERATIONS:
            return ToolResult.fail(
                f"Operation '{operation}' not permitted in Phase 1 read-only Git tool."
            )

        ws = kwargs.get("workspace_path") or self.workspace_path
        cwd_param = kwargs.get("cwd") or "."
        try:
            safe_cwd = resolve_safe_path(cwd_param, ws)
        except PermissionError as pe:
            return ToolResult.fail(str(pe))

        extra_args = kwargs.get("args") or []
        if isinstance(extra_args, str):
            extra_args = extra_args.split()

        # Security check on extra args
        for arg in extra_args:
            for forbidden in FORBIDDEN_PATTERNS:
                if forbidden in arg.lower():
                    return ToolResult.fail(
                        f"Forbidden git flag or argument '{arg}': write/reset operations not allowed in Phase 1."
                    )

        base_cmd = ["git"]
        default_args = ALLOWED_GIT_OPERATIONS[op_name]
        if extra_args:
            # e.g. git log with custom args: git log <extra_args>
            cmd_args = base_cmd + [op_name] + extra_args
        else:
            cmd_args = base_cmd + default_args

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd_args,
                cwd=str(safe_cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=15.0)
            stdout_str = stdout_bytes.decode("utf-8", errors="replace")
            stderr_str = stderr_bytes.decode("utf-8", errors="replace")
            exit_code = proc.returncode if proc.returncode is not None else 0

            if exit_code == 0:
                return ToolResult.ok(
                    stdout=stdout_str,
                    exit_code=0,
                    data={"operation": op_name, "output": stdout_str, "cwd": str(safe_cwd)},
                )
            else:
                return ToolResult.fail(
                    error=f"Git {op_name} failed with exit code {exit_code}",
                    stderr=stderr_str,
                    exit_code=exit_code,
                    metadata={"stdout": stdout_str},
                )
        except asyncio.TimeoutError:
            return ToolResult.fail(f"Git {op_name} timed out after 15 seconds")
        except Exception as e:
            return ToolResult.fail(f"Git execution error: {e}")


def register_git_tools(registry: ToolRegistry, workspace_path: Path | None = None) -> None:
    """Registers the read-only Git inspection tool in ToolRegistry."""
    tool = GitTool(workspace_path)
    if registry.exists(tool.name):
        registry.replace(tool)
    else:
        registry.register(tool)
