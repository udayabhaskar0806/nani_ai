"""N.A.N.I. V2 — Bounded Subprocess Supervisor and Execution Isolation Adapter
Provides:
1. Streaming bounded stdout/stderr consumption (preventing memory exhaustion).
2. Monotonic timeout termination and complete process-group reaping.
3. Task-scoped process tracking and identity verification.
4. Enforceable Linux namespace isolation (bwrap) with fail-closed default.
5. Strict environment allowlist stripping parent credentials.
"""

import asyncio
import os
import shutil
import signal
import time
from collections import defaultdict
from pathlib import Path

from nani.tools.result import ToolResult

MAX_BUFFER_BYTES = 100_000
HARD_FLOOD_LIMIT_BYTES = 10_000_000
DEFAULT_TIMEOUT_SECONDS = 30.0


class ProcessRegistry:
    """Tracks task-spawned processes to prevent unauthorized cross-process signaling."""

    def __init__(self) -> None:
        self._task_processes: dict[str, set[int]] = defaultdict(set)

    def register(self, task_id: str, pid: int) -> None:
        self._task_processes[task_id].add(pid)

    def unregister(self, task_id: str, pid: int) -> None:
        if task_id in self._task_processes:
            self._task_processes[task_id].discard(pid)

    def is_owned_by_task(self, task_id: str, pid: int) -> bool:
        return pid in self._task_processes.get(task_id, set())

    def get_task_pids(self, task_id: str) -> set[int]:
        return set(self._task_processes.get(task_id, set()))

    def clear_task(self, task_id: str) -> None:
        if task_id in self._task_processes:
            del self._task_processes[task_id]


# Global process registry
process_registry = ProcessRegistry()


class ExecutionIsolationAdapter:
    """Manages enforceable filesystem and network isolation for autonomous command execution."""

    @classmethod
    def is_bwrap_available(cls) -> bool:
        bwrap_path = shutil.which("bwrap")
        if not bwrap_path:
            return False
        # Verify bwrap can run in this environment
        try:
            import subprocess

            res = subprocess.run(
                [bwrap_path, "--ro-bind", "/", "/", "--dev", "/dev", "true"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2,
            )
            return res.returncode == 0
        except Exception:
            return False

    @classmethod
    def wrap_isolated_command(
        cls,
        argv: list[str],
        workspace: Path,
        cwd: Path | None = None,
        network_allowed: bool = False,
        allow_unsandboxed: bool = False,
    ) -> tuple[list[str], bool, str]:
        """Wraps argv in bwrap sandbox enforcing read-only root and read-write workspace only.

        Returns (wrapped_argv, success, reason).
        """
        if allow_unsandboxed or os.environ.get("NANI_ALLOW_UNSANDBOXED_FOR_TESTS") == "1":
            return (argv, True, "EXPLICIT_UNSANDBOXED_AUTHORIZED")

        if not cls.is_bwrap_available():
            return (
                argv,
                False,
                "ISOLATION_UNAVAILABLE: Unsandboxed arbitrary execution is denied by default. Linux sandbox (bwrap) unavailable.",
            )

        ws_str = str(workspace.resolve())
        target_cwd = str((cwd or workspace).resolve())
        # Base bwrap isolation flags
        wrapped = [
            "bwrap",
            "--ro-bind",
            "/",
            "/",
            "--bind",
            ws_str,
            ws_str,
            "--dev",
            "/dev",
            "--proc",
            "/proc",
            "--die-with-parent",
        ]

        # Mount user runtime directory (for X11, D-Bus session bus, audio, Wayland)
        uid = os.getuid() if hasattr(os, "getuid") else None
        if uid is not None:
            user_run_dir = Path(f"/run/user/{uid}")
            if user_run_dir.exists():
                wrapped.extend(["--bind", str(user_run_dir), str(user_run_dir)])
        x11_unix = Path("/tmp/.X11-unix")
        if x11_unix.exists():
            wrapped.extend(["--bind", str(x11_unix), str(x11_unix)])

        if not network_allowed:
            wrapped.append("--unshare-net")

        # Set chdir to target working directory inside sandbox
        wrapped.extend(["--chdir", target_cwd])
        wrapped.extend(argv)
        return (wrapped, True, "OK")


class SubprocessSupervisor:
    """Shared supervisor managing child processes with bounded streaming and clean teardown."""

    @staticmethod
    def get_sanitized_env(workspace: Path) -> dict[str, str]:
        """Produces a strictly allowlisted environment stripping parent secrets and credentials."""
        tmp_dir = workspace / ".tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        env = {
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "TMPDIR": str(tmp_dir),
            "HOME": os.environ.get("HOME", str(workspace)),
        }
        # Desktop GUI & session bus pass-through for terminal and window dispatch
        for k in (
            "DISPLAY",
            "WAYLAND_DISPLAY",
            "XAUTHORITY",
            "DBUS_SESSION_BUS_ADDRESS",
            "XDG_RUNTIME_DIR",
            "XDG_CURRENT_DESKTOP",
            "XDG_SESSION_TYPE",
            "XDG_SESSION_DESKTOP",
            "DESKTOP_SESSION",
            "USER",
            "SHELL",
            "TERM",
        ):
            if k in os.environ:
                env[k] = os.environ[k]
        return env

    @staticmethod
    async def _read_stream(
        stream: asyncio.StreamReader,
        max_bytes: int = MAX_BUFFER_BYTES,
        hard_limit: int = HARD_FLOOD_LIMIT_BYTES,
    ) -> tuple[bytes, bool, bool]:
        """Reads stream in chunks. Returns (buffer, was_truncated, was_flood_killed)."""
        buffer = bytearray()
        total_read = 0
        truncated = False
        flood_killed = False

        while True:
            chunk = await stream.read(4096)
            if not chunk:
                break
            total_read += len(chunk)
            if len(buffer) < max_bytes:
                space_left = max_bytes - len(buffer)
                buffer.extend(chunk[:space_left])
            else:
                truncated = True

            if total_read > hard_limit:
                flood_killed = True
                truncated = True
                break

        return bytes(buffer), truncated, flood_killed

    @classmethod
    async def run_supervised(
        cls,
        argv: list[str],
        cwd: Path,
        workspace: Path,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        env: dict[str, str] | None = None,
        task_id: str | None = None,
        isolated: bool = True,
        network_allowed: bool = False,
        allow_unsandboxed: bool = False,
    ) -> ToolResult:
        """Runs a subprocess with full supervision, bounded streaming, and timeout cleanup."""
        t_start = time.monotonic()
        effective_env = env or cls.get_sanitized_env(workspace)

        final_argv = argv
        if isolated:
            wrapped, ok, err_reason = ExecutionIsolationAdapter.wrap_isolated_command(
                argv,
                workspace,
                cwd=cwd,
                network_allowed=network_allowed,
                allow_unsandboxed=allow_unsandboxed,
            )
            if not ok:
                return ToolResult.fail(
                    error=err_reason,
                    metadata={"isolation_failure": True},
                )
            final_argv = wrapped

        proc: asyncio.subprocess.Process | None = None
        pgid: int | None = None

        try:
            proc = await asyncio.create_subprocess_exec(
                *final_argv,
                cwd=str(cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=effective_env,
                start_new_session=True,
            )

            if proc.pid:
                pgid = proc.pid
                if task_id:
                    process_registry.register(task_id, proc.pid)

            # Concurrently read stdout and stderr with timeout
            stdout_task = asyncio.create_task(cls._read_stream(proc.stdout))  # type: ignore[arg-type]
            stderr_task = asyncio.create_task(cls._read_stream(proc.stderr))  # type: ignore[arg-type]
            wait_task = asyncio.create_task(proc.wait())

            done, pending = await asyncio.wait(
                [
                    wait_task,
                    stdout_task,
                    stderr_task,
                ],
                timeout=timeout,
                return_when=asyncio.ALL_COMPLETED,
            )

            for t in pending:
                t.cancel()

            # Check if timeout occurred
            if proc.returncode is None:
                raise asyncio.TimeoutError(f"Process timed out after {timeout} seconds")

            stdout_bytes, stdout_trunc, stdout_flood = (
                stdout_task.result() if stdout_task.done() else (b"", False, False)
            )
            stderr_bytes, stderr_trunc, stderr_flood = (
                stderr_task.result() if stderr_task.done() else (b"", False, False)
            )

            if stdout_flood or stderr_flood:
                cls._kill_pgid(pgid)
                return ToolResult.fail(
                    error="Command terminated: exceeded maximum output flood limit.",
                    exit_code=-9,
                    duration_ms=int((time.monotonic() - t_start) * 1000),
                )

            stdout_str = stdout_bytes.decode("utf-8", errors="replace")
            stderr_str = stderr_bytes.decode("utf-8", errors="replace")

            if stdout_trunc:
                stdout_str += "\n[...OUTPUT TRUNCATED: BUFFER LIMIT EXCEEDED...]"
            if stderr_trunc:
                stderr_str += "\n[...STDERR TRUNCATED: BUFFER LIMIT EXCEEDED...]"

            duration_ms = int((time.monotonic() - t_start) * 1000)
            exit_code = proc.returncode

            if exit_code == 0:
                return ToolResult.ok(
                    stdout=stdout_str,
                    exit_code=0,
                    duration_ms=duration_ms,
                    data={"cwd": str(cwd)},
                )
            else:
                return ToolResult.fail(
                    error=f"Command exited with non-zero code {exit_code}",
                    stdout=stdout_str,
                    stderr=stderr_str,
                    exit_code=exit_code,
                    duration_ms=duration_ms,
                    metadata={"stdout": stdout_str, "cwd": str(cwd)},
                )

        except (asyncio.TimeoutError, asyncio.CancelledError) as exc:
            duration_ms = int((time.monotonic() - t_start) * 1000)
            cls._kill_pgid(pgid)
            if proc:
                try:
                    await asyncio.wait_for(proc.wait(), timeout=1.0)
                except Exception:
                    pass

            is_timeout = isinstance(exc, asyncio.TimeoutError)
            err_msg = (
                f"Command timed out after {timeout} seconds"
                if is_timeout
                else "Command was cancelled by operator"
            )
            return ToolResult.fail(
                error=err_msg,
                exit_code=-1,
                duration_ms=duration_ms,
                metadata={"timeout": is_timeout, "cancelled": not is_timeout},
            )

        except Exception as e:
            duration_ms = int((time.monotonic() - t_start) * 1000)
            cls._kill_pgid(pgid)
            return ToolResult.fail(
                error=f"Subprocess execution error: {e}",
                duration_ms=duration_ms,
            )

        finally:
            if task_id and proc and proc.pid:
                process_registry.unregister(task_id, proc.pid)

    @staticmethod
    def _kill_pgid(pgid: int | None) -> None:
        if not pgid or pgid <= 1:
            return
        try:
            os.killpg(pgid, signal.SIGTERM)
            time.sleep(0.05)
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
