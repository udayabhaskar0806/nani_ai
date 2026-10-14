"""N.A.N.I. V2 — Structured Git Inspection Native Tool
Provides read-only local Git repository inspection (status, diff, log, branch, show, rev-parse).
Strictly blocks destructive, mutative, or remote operations via positive schemas.
"""

import re
from pathlib import Path
from typing import Any

from nani.core.context import ExecutionContext
from nani.core.task import RiskLevel, WorkerCapability
from nani.tools.path_utils import resolve_safe_path
from nani.tools.registry import BaseTool, ToolRegistry
from nani.tools.result import ToolResult
from nani.tools.supervisor import SubprocessSupervisor

SAFE_REF_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\./~^@{}]+$")
FORBIDDEN_KEYWORDS = [
    "push",
    "reset",
    "clean",
    "checkout",
    "commit",
    "merge",
    "rebase",
    "pull",
    "rm",
]


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
                    "enum": ["status", "diff", "log", "branch", "show", "rev_parse", "rev-parse"],
                },
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional safe ref targets (e.g. ['HEAD~1'], ['main'])",
                },
                "cwd": {"type": "string", "description": "Repository directory within workspace"},
                "max_count": {"type": "integer", "description": "Max log entries", "default": 10},
            },
            "required": ["operation"],
        }

    async def run(self, **kwargs: Any) -> ToolResult:
        context: ExecutionContext | None = kwargs.pop("context", None)
        operation = kwargs.get("operation")
        if not operation:
            return ToolResult.fail("Missing required parameter: 'operation'")

        op_name = str(operation).strip().lower().replace("_", "-")

        if context and context.workspace:
            ws = context.workspace
        elif self.workspace_path:
            ws = self.workspace_path.resolve()
        else:
            ws = Path.cwd().resolve()

        cwd_param = kwargs.get("cwd") or "."
        try:
            safe_cwd = resolve_safe_path(cwd_param, ws)
        except PermissionError as pe:
            return ToolResult.fail(str(pe))

        extra_args = kwargs.get("args") or []
        if isinstance(extra_args, str):
            extra_args = extra_args.split()

        # Check for forbidden arguments
        for arg in extra_args:
            arg_str = str(arg).strip()
            if any(forbidden in arg_str.lower() for forbidden in FORBIDDEN_KEYWORDS):
                return ToolResult.fail(
                    f"Forbidden argument '{arg_str}': write/reset operations not allowed in Phase 1."
                )
            if arg_str.startswith("-"):
                return ToolResult.fail(
                    f"Forbidden flag or option '{arg_str}': custom options not permitted in read-only mode."
                )
            if not SAFE_REF_PATTERN.match(arg_str):
                return ToolResult.fail(f"Forbidden characters in Git target argument '{arg_str}'.")

        # Base safe command with disabled hooks, isolated configuration, and no pager
        base_cmd = [
            "git",
            "--no-pager",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "safe.directory=*",
        ]

        # Operation construction via positive allowlist
        if op_name == "status":
            if extra_args:
                return ToolResult.fail(
                    "Forbidden: git status does not accept additional arguments."
                )
            cmd_args = base_cmd + ["status", "--short"]

        elif op_name == "branch":
            if extra_args:
                return ToolResult.fail(
                    "Forbidden: git branch does not accept arguments. Only listing is permitted in read-only mode."
                )
            cmd_args = base_cmd + ["branch", "--list", "-a"]

        elif op_name == "diff":
            cmd_args = (
                base_cmd
                + [
                    "diff",
                    "--no-ext-diff",
                    "--no-textconv",
                ]
                + list(extra_args)
            )

        elif op_name == "log":
            max_count = int(kwargs.get("max_count", 10))
            if max_count <= 0 or max_count > 1000:
                max_count = 10
            cmd_args = (
                base_cmd
                + [
                    "log",
                    f"-n{max_count}",
                    "--oneline",
                ]
                + list(extra_args)
            )

        elif op_name == "show":
            cmd_args = (
                base_cmd
                + [
                    "show",
                    "--no-ext-diff",
                    "--no-textconv",
                    "--stat",
                ]
                + list(extra_args)
            )

        elif op_name == "rev-parse":
            target = extra_args[0] if extra_args else "HEAD"
            cmd_args = base_cmd + ["rev-parse", target]

        else:
            return ToolResult.fail(
                f"Operation '{operation}' not permitted in Phase 1 read-only Git tool."
            )

        git_env = {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "HOME": "/dev/null",
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "LC_ALL": "C.UTF-8",
        }

        task_id = context.task_id if context else None
        return await SubprocessSupervisor.run_supervised(
            argv=cmd_args,
            cwd=safe_cwd,
            workspace=ws,
            timeout=15.0,
            env=git_env,
            task_id=task_id,
            isolated=False,
        )


def register_git_tools(registry: ToolRegistry, workspace_path: Path | None = None) -> None:
    """Registers the read-only Git inspection tool in ToolRegistry."""
    tool = GitTool(workspace_path)
    if registry.exists(tool.name):
        registry.replace(tool)
    else:
        registry.register(tool)
