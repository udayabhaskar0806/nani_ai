"""N.A.N.I. V2 — Process Inspection and Control Native Tool
Provides safe process listing, inspection, spawning, and termination.
Strictly protects NANI runtime and init processes from termination.
"""

import asyncio
import os
from pathlib import Path
from typing import Any

from nani.core.task import RiskLevel, WorkerCapability
from nani.tools.filesystem import resolve_safe_path
from nani.tools.registry import BaseTool, ToolRegistry
from nani.tools.result import ToolResult


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
                    "description": "Signal number to send",
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
        operation = kwargs.get("operation")
        if not operation:
            return ToolResult.fail("Missing required parameter: 'operation'")

        op_name = str(operation).strip().lower()

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
            return await self._start_process(str(cmd), str(cwd), kwargs.get("workspace_path"))
        elif op_name == "terminate_process":
            pid = kwargs.get("pid")
            if pid is None:
                return ToolResult.fail("Missing required parameter 'pid' for terminate_process")
            sig = int(kwargs.get("signal", 15))
            return await self._terminate_process(int(pid), sig)
        else:
            return ToolResult.fail(f"Unknown process operation: '{operation}'")

    async def _list_processes(self, limit: int) -> ToolResult:
        try:
            proc = await asyncio.create_subprocess_exec(
                "ps",
                "-eo",
                "pid,ppid,comm,%cpu,%mem",
                "--sort=-%cpu",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, _ = await proc.communicate()
            lines = stdout_bytes.decode("utf-8", errors="replace").splitlines()
            processes = []
            for line in lines[1 : limit + 1]:
                parts = line.strip().split(None, 4)
                if len(parts) >= 5:
                    processes.append(
                        {
                            "pid": int(parts[0]),
                            "ppid": int(parts[1]),
                            "comm": parts[2],
                            "cpu": parts[3],
                            "mem": parts[4],
                        }
                    )
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
            stdout_bytes, _ = await proc.communicate()
            lines = stdout_bytes.decode("utf-8", errors="replace").splitlines()
            if len(lines) < 2:
                return ToolResult.fail(f"Process {pid} not found.")

            parts = lines[1].strip().split(None, 4)
            return ToolResult.ok(
                data={
                    "pid": int(parts[0]),
                    "ppid": int(parts[1]),
                    "user": parts[2],
                    "stat": parts[3],
                    "comm": parts[4] if len(parts) > 4 else "",
                }
            )
        except Exception as e:
            return ToolResult.fail(f"Failed to get info for PID {pid}: {e}")

    async def _start_process(self, cmd: str, cwd: str, ws_override: str | None) -> ToolResult:
        try:
            ws = ws_override or self.workspace_path
            safe_cwd = resolve_safe_path(cwd, ws)
            proc = await asyncio.create_subprocess_shell(
                cmd,
                cwd=str(safe_cwd),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                start_new_session=True,
            )
            return ToolResult.ok(data={"pid": proc.pid, "command": cmd, "cwd": str(safe_cwd)})
        except PermissionError as pe:
            return ToolResult.fail(str(pe))
        except Exception as e:
            return ToolResult.fail(f"Failed to start process: {e}")

    async def _terminate_process(self, pid: int, sig: int) -> ToolResult:
        if self._is_protected_pid(pid):
            return ToolResult.fail(
                f"Refusing to terminate protected NANI or OS runtime process (PID {pid})."
            )

        try:
            os.kill(pid, sig)
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
