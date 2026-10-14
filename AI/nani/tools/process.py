"""N.A.N.I. V2 — Process Inspection and Control Native Tool
Provides safe process listing, inspection, spawning, and termination.
Strictly scopes process termination to task-owned processes and protects runtime processes.
"""

import asyncio
import os
import signal
from pathlib import Path
from typing import Any

from nani.core.context import ExecutionContext
from nani.core.task import RiskLevel, WorkerCapability
from nani.tools.path_utils import resolve_safe_path
from nani.tools.registry import BaseTool, ToolRegistry
from nani.tools.result import ToolResult
from nani.tools.supervisor import ExecutionIsolationAdapter, process_registry

ALLOWED_SIGNALS = {
    int(signal.SIGTERM): "SIGTERM",
    int(signal.SIGKILL): "SIGKILL",
    int(signal.SIGINT): "SIGINT",
}


class ProcessTool(BaseTool):
    def __init__(self, workspace_path: Path | None = None) -> None:
        self.workspace_path = workspace_path

    @property
    def name(self) -> str:
        return "process"

    @property
    def description(self) -> str:
        return "Manages and inspects operating system processes (list, info, start, terminate)."

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
                "operation": {
                    "type": "string",
                    "enum": [
                        "list_processes",
                        "process_info",
                        "start_process",
                        "terminate_process",
                    ],
                },
                "pid": {"type": "integer", "description": "Target process ID"},
                "cmd": {"type": "string", "description": "Command string to spawn"},
                "cwd": {"type": "string", "description": "Working directory for spawned process"},
                "signal": {
                    "type": "integer",
                    "description": "Signal number to send (15=SIGTERM, 9=SIGKILL, 2=SIGINT)",
                    "default": 15,
                },
                "limit": {
                    "type": "integer",
                    "description": "Max processes to return",
                    "default": 50,
                },
            },
            "required": ["operation"],
        }

    def _is_protected_pid(self, pid: int) -> bool:
        """Determines if target PID belongs to NANI or core OS init."""
        nani_pid = os.getpid()
        nani_ppid = os.getppid()
        return pid <= 1 or pid in (nani_pid, nani_ppid)

    async def run(self, **kwargs: Any) -> ToolResult:
        context: ExecutionContext | None = kwargs.pop("context", None)
        operation = kwargs.get("operation")
        if not operation:
            return ToolResult.fail("Missing required parameter: 'operation'")

        op_name = str(operation).strip().lower()

        if context and context.workspace:
            ws = context.workspace
        elif self.workspace_path:
            ws = self.workspace_path.resolve()
        else:
            ws = Path.cwd().resolve()

        if op_name == "list_processes":
            return await self._list_processes(int(kwargs.get("limit", 50)))
        elif op_name == "process_info":
            pid = kwargs.get("pid")
            if pid is None:
                return ToolResult.fail("Missing required parameter 'pid' for process_info")
            return await self._process_info(int(pid))
        elif op_name == "start_process":
            cmd = kwargs.get("cmd")
            if not cmd:
                return ToolResult.fail("Missing required parameter 'cmd' for start_process")
            cwd = kwargs.get("cwd") or "."
            task_id = context.task_id if context else None
            allow_unsandboxed = bool(context and context.metadata.get("allow_unsandboxed", False))
            return await self._start_process(
                str(cmd), str(cwd), ws, task_id, allow_unsandboxed=allow_unsandboxed
            )
        elif op_name == "terminate_process":
            pid = kwargs.get("pid")
            if pid is None:
                return ToolResult.fail("Missing required parameter 'pid' for terminate_process")
            sig = int(kwargs.get("signal", 15))
            task_id = context.task_id if context else None
            return await self._terminate_process(int(pid), sig, task_id)
        else:
            return ToolResult.fail(f"Unknown process operation: '{operation}'")

    async def _list_processes(self, limit: int) -> ToolResult:
        try:
            # First attempt with standard ps options
            proc = await asyncio.create_subprocess_exec(
                "ps",
                "-eo",
                "pid,ppid,comm,%cpu,%mem",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await proc.communicate()
            if proc.returncode != 0:
                # Fallback to minimal ps args for busybox or minimal container environments
                proc = await asyncio.create_subprocess_exec(
                    "ps",
                    "-o",
                    "pid,ppid,comm",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout_bytes, stderr_bytes = await proc.communicate()
                if proc.returncode != 0:
                    stderr_str = stderr_bytes.decode("utf-8", errors="replace").strip()
                    return ToolResult.fail(
                        f"ps command failed with exit code {proc.returncode}: {stderr_str or 'Process inspection error'}"
                    )

            lines = stdout_bytes.decode("utf-8", errors="replace").splitlines()
            processes = []
            for line in lines[1:]:
                parts = line.strip().split(None, 4)
                if len(parts) >= 3:
                    try:
                        p_entry = {
                            "pid": int(parts[0]),
                            "ppid": int(parts[1]),
                            "comm": parts[2],
                            "cpu": parts[3] if len(parts) > 3 else "0.0",
                            "mem": parts[4] if len(parts) > 4 else "0.0",
                        }
                        processes.append(p_entry)
                        if len(processes) >= limit:
                            break
                    except ValueError:
                        continue

            return ToolResult.ok(data={"processes": processes, "count": len(processes)})
        except Exception as e:
            return ToolResult.fail(f"Failed to list processes: {e}")

    async def _process_info(self, pid: int) -> ToolResult:
        try:
            proc = await asyncio.create_subprocess_exec(
                "ps",
                "-p",
                str(pid),
                "-o",
                "pid,ppid,user,stat,comm",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await proc.communicate()
            if proc.returncode != 0:
                stderr_str = stderr_bytes.decode("utf-8", errors="replace").strip()
                return ToolResult.fail(
                    f"ps info failed with exit code {proc.returncode}: {stderr_str or 'Process not found'}"
                )

            lines = stdout_bytes.decode("utf-8", errors="replace").splitlines()
            if len(lines) < 2:
                return ToolResult.fail(f"Process {pid} not found.")

            parts = lines[1].strip().split(None, 4)
            if len(parts) < 1:
                return ToolResult.fail(f"Process {pid} info unparseable.")

            return ToolResult.ok(
                data={
                    "pid": int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else pid,
                    "ppid": int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0,
                    "user": parts[2] if len(parts) > 2 else "unknown",
                    "stat": parts[3] if len(parts) > 3 else "unknown",
                    "comm": parts[4] if len(parts) > 4 else "",
                }
            )
        except Exception as e:
            return ToolResult.fail(f"Failed to get info for PID {pid}: {e}")

    async def _start_process(
        self,
        cmd: str,
        cwd: str,
        workspace: Path,
        task_id: str | None,
        allow_unsandboxed: bool = False,
    ) -> ToolResult:
        try:
            safe_cwd = resolve_safe_path(cwd, workspace)
            wrapped_cmd, is_isolated, reason = ExecutionIsolationAdapter.wrap_isolated_command(
                ["/bin/sh", "-c", cmd],
                workspace,
                cwd=safe_cwd,
                network_allowed=False,
                allow_unsandboxed=allow_unsandboxed,
            )
            if not is_isolated:
                return ToolResult.fail(
                    f"ISOLATION_UNAVAILABLE: Unsandboxed arbitrary process execution is denied by default. {reason}"
                )

            proc = await asyncio.create_subprocess_exec(
                *wrapped_cmd,
                cwd=str(safe_cwd),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                start_new_session=True,
            )
            if task_id and proc.pid:
                process_registry.register(task_id, proc.pid)
            return ToolResult.ok(data={"pid": proc.pid, "command": cmd, "cwd": str(safe_cwd)})
        except PermissionError as pe:
            return ToolResult.fail(str(pe))
        except Exception as e:
            return ToolResult.fail(f"Failed to start process: {e}")

    async def _terminate_process(self, pid: int, sig: int, task_id: str | None) -> ToolResult:
        if self._is_protected_pid(pid):
            return ToolResult.fail(
                f"Refusing to terminate protected NANI or OS runtime process (PID {pid})."
            )

        if sig not in ALLOWED_SIGNALS:
            return ToolResult.fail(
                f"Signal {sig} not permitted. Allowed signals: SIGTERM(15), SIGKILL(9), SIGINT(2)."
            )

        # Enforce task-scoped termination when running within a task context
        if task_id and not process_registry.is_owned_by_task(task_id, pid):
            return ToolResult.fail(
                f"Access denied: PID {pid} is not owned by task '{task_id}'. Process control is strictly task-scoped."
            )

        try:
            os.kill(pid, sig)
            if task_id:
                process_registry.unregister(task_id, pid)
            return ToolResult.ok(data={"pid": pid, "signal": sig, "status": "signal_sent"})
        except ProcessLookupError:
            return ToolResult.fail(f"Process {pid} does not exist.")
        except PermissionError:
            return ToolResult.fail(f"Permission denied to terminate PID {pid}.")
        except Exception as e:
            return ToolResult.fail(f"Error terminating PID {pid}: {e}")


def register_process_tools(registry: ToolRegistry, workspace_path: Path | None = None) -> None:
    """Registers process management tools in the ToolRegistry."""
    tool = ProcessTool(workspace_path)
    if registry.exists(tool.name):
        registry.replace(tool)
    else:
        registry.register(tool)
