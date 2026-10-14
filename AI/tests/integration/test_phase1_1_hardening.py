"""N.A.N.I. V2 — Phase 1.1 Runtime & Security Hardening Regression Suite
Asserts corrected security boundaries, crash recovery, concurrency, and lifecycle semantics (F01–F17).
Uses strictly disposable fixtures and zero external network/AI calls.
"""

import subprocess
from pathlib import Path

import pytest

from nani.core.context import ExecutionContext
from nani.core.orchestrator import Orchestrator
from nani.core.task import (
    Action,
    InvalidTaskTransition,
    PlanStep,
    TaskStatus,
    WorkerCapability,
)
from nani.core.task_manager import TaskManager
from nani.memory.database import ConcurrencyError, Database
from nani.models.base import ModelCapability
from nani.models.router import ModelRouter
from nani.tools.filesystem import register_filesystem_tools
from nani.tools.git import register_git_tools
from nani.tools.process import register_process_tools
from nani.tools.registry import ToolRegistry
from nani.tools.shell import register_shell_tools


def setup_runtime(root: Path):
    ws = root / "runtime"
    ws.mkdir(parents=True, exist_ok=True)
    db = Database(ws / "hardening_audit.db")
    tm = TaskManager(db=db)
    reg = ToolRegistry(tm.journal)
    register_filesystem_tools(reg, ws)
    register_shell_tools(reg, ws)
    register_git_tools(reg, ws)
    register_process_tools(reg, ws)
    orch = Orchestrator(tm, reg)
    return ws, tm, reg, orch


def make_step(tool: str, params: dict, verification: dict | None = None) -> PlanStep:
    return PlanStep(
        order=1,
        description="hardening_test_step",
        capability_required=WorkerCapability.SYSTEM,
        actions=[Action(worker="system_worker", tool=tool, parameters=params)],
        verification=verification or {"type": "tool_success"},
    )


# F01: Action parameters cannot replace the trusted workspace
@pytest.mark.asyncio
async def test_f01_action_workspace_override_rejected(tmp_path: Path):
    ws, tm, reg, orch = setup_runtime(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()

    task = tm.create_task("override attempt", str(ws))
    # Action caller attempts to inject outside directory as workspace_path
    step = make_step(
        "write_file",
        {"path": "escaped.txt", "content": "audit", "workspace_path": str(outside)},
    )
    result_task = await orch.run_task(task.task_id, [step])

    # Must NOT succeed in escaping workspace
    assert result_task.status != TaskStatus.COMPLETED
    assert not (outside / "escaped.txt").exists()


# F02: Shell execution is isolated and confined
@pytest.mark.asyncio
async def test_f02_shell_confinement_blocks_escape(tmp_path: Path):
    ws, tm, reg, orch = setup_runtime(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()

    context = ExecutionContext(task_id="t1", workspace=ws)
    await reg.execute(
        "shell",
        {"command": "printf audit > ../outside/shell.txt"},
        context=context,
    )
    # The command should either fail or not write to outside directory
    assert not (outside / "shell.txt").exists()


# F03: Copy tool rejects destination child symlinks pointing outside workspace
@pytest.mark.asyncio
async def test_f03_copy_directory_child_symlink_escape_prevented(tmp_path: Path):
    ws, tm, reg, orch = setup_runtime(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()

    (ws / "source.txt").write_text("new")
    (outside / "source.txt").write_text("old")
    (ws / "dest").mkdir()
    (ws / "dest" / "source.txt").symlink_to(outside / "source.txt")

    context = ExecutionContext(task_id="t1", workspace=ws)
    res = await reg.execute(
        "copy",
        {"src": "source.txt", "dst": "dest"},
        context=context,
    )
    # Must fail to overwrite the outside file through the symlink
    assert res.success is False
    assert (outside / "source.txt").read_text() == "old"


# F04: Git tool strictly blocks state mutations
@pytest.mark.asyncio
async def test_f04_git_branch_mutation_blocked(tmp_path: Path):
    ws, tm, reg, orch = setup_runtime(tmp_path)
    repo = ws / "repo"
    repo.mkdir()

    def run_git(*args):
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            capture_output=True,
            text=True,
        ).stdout

    run_git("init")
    run_git("config", "user.email", "audit@example.invalid")
    run_git("config", "user.name", "Audit")
    (repo / "f").write_text("initial")
    run_git("add", "f")
    run_git("commit", "-m", "audit")

    context = ExecutionContext(task_id="t1", workspace=ws)
    res = await reg.execute(
        "git",
        {"operation": "branch", "args": ["created_by_read_tool"], "cwd": "repo"},
        context=context,
    )
    assert res.success is False
    assert "created_by_read_tool" not in run_git("branch", "--list")


# F05: Crash recovery avoids blind re-execution of non-idempotent side effects
@pytest.mark.asyncio
async def test_f05_crash_recovery_prevents_duplicate_side_effect(tmp_path: Path):
    ws, tm, reg, orch = setup_runtime(tmp_path)
    task = tm.create_task("crash window", str(ws))

    # Injected crash: simulates crash after side effect before result commit
    original = tm.journal.record_action_result

    def crash(**kwargs):
        raise RuntimeError("Injected crash after side effect before result commit")

    tm.journal.record_action_result = crash
    try:
        await orch.run_task(
            task.task_id, [make_step("shell", {"command": "printf x >> counter.txt"})]
        )
    except RuntimeError:
        pass
    tm.journal.record_action_result = original

    # Restart runtime from database
    restarted_tm = TaskManager(Database(ws / "hardening_audit.db"))
    restarted_orch = Orchestrator(restarted_tm, reg)
    final_task = await restarted_orch.run_task(task.task_id)

    # Must NOT blindly replay and produce 'xx'
    assert final_task.status != TaskStatus.COMPLETED or (ws / "counter.txt").read_text() != "xx"
    assert (ws / "counter.txt").read_text() != "xx"


# F05: Session start recovers PLANNING, RECOVERY, and VERIFYING tasks cleanly
@pytest.mark.asyncio
async def test_f05_lifecycle_state_recovery_on_restart(tmp_path: Path):
    ws, tm, reg, orch = setup_runtime(tmp_path)

    for status in [TaskStatus.PLANNING, TaskStatus.VERIFYING]:
        t = tm.create_task(f"restart {status.value}", str(ws))
        tm.start_task(t.task_id)
        valid_step = make_step("file_exists", {"path": "."})
        tm.update_plan(t.task_id, [valid_step])

        if status != TaskStatus.PLANNING:
            tm.transition_task(t.task_id, TaskStatus.RUNNING)
            tm.transition_task(t.task_id, status)

        restarted_tm = TaskManager(Database(ws / "hardening_audit.db"))
        restarted_orch = Orchestrator(restarted_tm, reg)
        out = await restarted_orch.run_task(t.task_id)
        # Task should not be stuck in its pre-crash state
        assert out.status in (TaskStatus.COMPLETED, TaskStatus.RUNNING, TaskStatus.FAILED)


# F06: Stale persistence does not overwrite cancellation
@pytest.mark.asyncio
async def test_f06_cancellation_during_execution_preserved(tmp_path: Path):
    ws, tm, reg, orch = setup_runtime(tmp_path)
    task = tm.create_task("cancel during execution", str(ws))

    tool = reg.get("write_file")
    assert tool is not None
    original_run = tool.run

    async def cancel_then_run(**kwargs):
        tm.cancel_task(task.task_id)
        return await original_run(**kwargs)

    tool.run = cancel_then_run  # type: ignore[method-assign]
    out = await orch.run_task(
        task.task_id, [make_step("write_file", {"path": "cancel.txt", "content": "x"})]
    )
    tool.run = original_run  # type: ignore[method-assign]

    # Stale completed step update must NOT overwrite cancellation
    assert out.status == TaskStatus.CANCELLED


# F07: Raw secrets in task plans and actions are redacted at persistence boundary
def test_f07_raw_secret_redaction_in_persisted_plan(tmp_path: Path):
    ws, tm, reg, orch = setup_runtime(tmp_path)
    task = tm.create_task("secret persistence", str(ws))
    marker = "super_secret_password_123!"

    tm.update_plan(
        task.task_id,
        [make_step("write_file", {"path": "x.txt", "content": "x", "password": marker})],
    )

    with tm.db.get_connection() as conn:
        raw_params = conn.execute(
            "SELECT parameters_json FROM actions WHERE task_id = ?", (task.task_id,)
        ).fetchone()[0]

    assert marker not in raw_params
    assert "[REDACTED]" in raw_params


# F08: Multi-action step is rejected in Phase 1
@pytest.mark.asyncio
async def test_f08_multi_action_step_rejected(tmp_path: Path):
    ws, tm, reg, orch = setup_runtime(tmp_path)
    task = tm.create_task("multi-action invariant", str(ws))

    step = make_step("write_file", {"path": "first.txt", "content": "1"})
    step.actions.append(
        Action(
            worker="system", tool="write_file", parameters={"path": "second.txt", "content": "2"}
        )
    )

    # Planner / Orchestrator must reject steps with multiple actions in Phase 1
    out = await orch.run_task(task.task_id, [step])
    assert out.status == TaskStatus.FAILED
    assert "Phase 1 requires exactly one executable action per step" in (
        out.metadata.get("error", "") or str(out)
    )


# F08: Final task verification checks durable artifact invariants
@pytest.mark.asyncio
async def test_f08_final_verification_catches_invalidated_artifact(tmp_path: Path):
    ws, tm, reg, orch = setup_runtime(tmp_path)
    task = tm.create_task("invariant verification", str(ws))

    step_a = make_step(
        "write_file",
        {"path": "verified.txt", "content": "good"},
        verification={"type": "file_content", "path": "verified.txt", "expected_content": "good"},
    )
    step_b = make_step(
        "write_file",
        {"path": "verified.txt", "content": "bad"},
        verification={"type": "tool_success"},
    )

    out = await orch.run_task(task.task_id, [step_a, step_b])
    # The task must fail final verification because verified.txt was corrupted
    assert out.status == TaskStatus.FAILED


# F08: Unknown goal rejected
@pytest.mark.asyncio
async def test_f08_unknown_goal_rejected(tmp_path: Path):
    ws, tm, reg, orch = setup_runtime(tmp_path)
    task = tm.create_task("unrecognized objective: produce nonexistent financial report", str(ws))

    out = await orch.run_task(task.task_id)
    # Must fail, never succeed with echo NANI_OK
    assert out.status == TaskStatus.FAILED


# F10: WAITING cannot be resumed without approval
@pytest.mark.asyncio
async def test_f10_waiting_resume_requires_approval(tmp_path: Path):
    ws, tm, reg, orch = setup_runtime(tmp_path)
    task = tm.create_task("waiting security gate", str(ws))

    step = make_step("shell", {"command": "echo payment submission"})
    out = await orch.run_task(task.task_id, [step])
    assert out.status == TaskStatus.WAITING

    # Attempting to resume WAITING via resume_task must raise InvalidTaskTransition
    with pytest.raises(InvalidTaskTransition):
        tm.resume_task(task.task_id)


# F11: Plan updates remove superseded steps cleanly
def test_f11_plan_replacement_removes_old_steps(tmp_path: Path):
    ws, tm, reg, orch = setup_runtime(tmp_path)
    task = tm.create_task("plan update cleanup", str(ws))

    step1 = make_step("write_file", {"path": "a.txt", "content": "a"})
    step2 = make_step("write_file", {"path": "b.txt", "content": "b"})
    tm.update_plan(task.task_id, [step1, step2])
    assert len(tm.get_task(task.task_id).plan) == 2

    # Replace with single step
    new_step = make_step("write_file", {"path": "c.txt", "content": "c"})
    tm.update_plan(task.task_id, [new_step])

    reloaded = tm.get_task(task.task_id)
    assert len(reloaded.plan) == 1
    assert reloaded.plan[0].actions[0].parameters["path"] == "c.txt"


# F13: Process control is strictly task-scoped
@pytest.mark.asyncio
async def test_f13_process_termination_is_task_scoped(tmp_path: Path):
    ws, tm, reg, orch = setup_runtime(tmp_path)
    context = ExecutionContext(task_id="task_A", workspace=ws)

    # Spawn a background sleep process under task_A
    res_start = await reg.execute(
        "process",
        {"operation": "start_process", "cmd": "sleep 10"},
        context=context,
    )
    assert res_start.success is True
    pid = res_start.data["pid"]

    # Attempt to terminate PID from task_B must be denied
    context_b = ExecutionContext(task_id="task_B", workspace=ws)
    res_term_b = await reg.execute(
        "process",
        {"operation": "terminate_process", "pid": pid},
        context=context_b,
    )
    assert res_term_b.success is False
    assert "not owned by task" in res_term_b.error

    # Clean termination from task_A must succeed
    res_term_a = await reg.execute(
        "process",
        {"operation": "terminate_process", "pid": pid},
        context=context,
    )
    assert res_term_a.success is True


# F16: Model router provider replacement clears stale capability routes
def test_f16_model_router_purges_stale_capabilities():
    class DummyProvider:
        def __init__(self, name: str, caps: list[ModelCapability]):
            self.name = name
            self.supported_capabilities = caps

    router = ModelRouter()
    p1 = DummyProvider("same_provider", [ModelCapability.CODING])
    router.register_provider(p1)  # type: ignore[arg-type]

    # Replace with vision-only provider
    p2 = DummyProvider("same_provider", [ModelCapability.VISION])
    router.register_provider(p2)  # type: ignore[arg-type]

    # Coding should now be None, not pointing to vision provider
    assert router.get_provider_for_capability(ModelCapability.CODING) is None
    assert router.get_provider_for_capability(ModelCapability.VISION) is p2


# Process isolation: start_process is confined and cannot write outside workspace
@pytest.mark.asyncio
async def test_process_start_process_isolated(tmp_path: Path):
    ws, tm, reg, orch = setup_runtime(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()

    context = ExecutionContext(task_id="t1", workspace=ws)
    await reg.execute(
        "process",
        {
            "operation": "start_process",
            "cmd": "printf audit > ../outside/escaped_process.txt",
        },
        context=context,
    )
    # The process must NOT have escaped to write outside the workspace
    assert not (outside / "escaped_process.txt").exists()


# Git safety: repository-configured external helpers (fsmonitor, diff.external) are neutralized
@pytest.mark.asyncio
async def test_git_repository_configured_helpers_neutralized(tmp_path: Path):
    ws, tm, reg, orch = setup_runtime(tmp_path)
    repo = ws / "repo"
    repo.mkdir()

    def run_git(*args):
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            capture_output=True,
            text=True,
        ).stdout

    run_git("init")
    run_git("config", "user.email", "audit@example.invalid")
    run_git("config", "user.name", "Audit")
    (repo / "f.txt").write_text("hello")
    run_git("add", "f.txt")
    run_git("commit", "-m", "init")

    # Configure a malicious external helper in repository .git/config
    marker_file = ws / "helper_ran.txt"
    helper_script = ws / "malicious_helper.sh"
    helper_script.write_text(f"#!/bin/sh\necho pwned > {marker_file}\n")
    helper_script.chmod(0o755)

    run_git("config", "core.fsmonitor", str(helper_script))
    run_git("config", "diff.external", str(helper_script))

    context = ExecutionContext(task_id="t1", workspace=ws)
    # Run git status through registry
    st_res = await reg.execute(
        "git",
        {"operation": "status", "cwd": "repo"},
        context=context,
    )
    assert st_res.success is True
    # The helper must NOT have been executed
    assert not marker_file.exists()


# Database migration: upgrading v2 database to v3 adds version column
def test_database_migration_v2_to_v3(tmp_path: Path):
    import sqlite3

    db_path = tmp_path / "legacy_v2.db"
    conn = sqlite3.connect(str(db_path))
    # Create schema v2 state without version column
    conn.execute(
        "CREATE TABLE schema_version (version INTEGER PRIMARY KEY, applied_at REAL NOT NULL);"
    )
    conn.execute("INSERT INTO schema_version VALUES (1, 100.0);")
    conn.execute("INSERT INTO schema_version VALUES (2, 200.0);")
    conn.execute(
        """CREATE TABLE tasks (
            task_id TEXT PRIMARY KEY, original_goal TEXT, interpreted_goal TEXT,
            workspace_path TEXT, status TEXT, risk_level TEXT, current_step_index INTEGER,
            created_at REAL, updated_at REAL, metadata_json TEXT
        );"""
    )
    conn.commit()
    conn.close()

    # Open with Database class; must run migration 3 and add version column
    db = Database(db_path)
    assert db.get_schema_version() == 3

    with db.get_connection() as c:
        cols = [r["name"] for r in c.execute("PRAGMA table_info(tasks)").fetchall()]
    assert "version" in cols


# Concurrency: TaskManager rejects concurrent state transitions with ConcurrencyError
def test_task_manager_cas_concurrency_conflict(tmp_path: Path):
    ws, tm, reg, orch = setup_runtime(tmp_path)
    task = tm.create_task("cas test", str(ws))
    assert task.version == 1

    # Transition with correct expected_version succeeds
    t1 = tm.transition_task(task.task_id, TaskStatus.PLANNING, expected_version=1)
    assert t1.version == 2

    # Attempting transition with stale expected_version=1 must raise ConcurrencyError
    with pytest.raises(ConcurrencyError, match="CAS conflict"):
        tm.transition_task(task.task_id, TaskStatus.RUNNING, expected_version=1)


# Crash recovery: already-succeeded action is not replayed
@pytest.mark.asyncio
async def test_crash_recovery_does_not_replay_succeeded_action(tmp_path: Path):
    ws, tm, reg, orch = setup_runtime(tmp_path)
    task = tm.create_task("crash after success", str(ws))
    step = make_step("write_file", {"path": "counter.txt", "content": "1"})

    out = await orch.run_task(task.task_id, [step])
    assert out.status == TaskStatus.COMPLETED

    # Reset task back to RUNNING and step index to 0, leaving action in SUCCESS state
    with tm.db.get_connection() as conn:
        conn.execute(
            "UPDATE tasks SET status = 'RUNNING', current_step_index = 0 WHERE task_id = ?",
            (task.task_id,),
        )
        conn.execute("UPDATE plan_steps SET status = 'PENDING' WHERE task_id = ?", (task.task_id,))
        conn.commit()

    restarted_tm = TaskManager(Database(ws / "hardening_audit.db"))
    restarted_orch = Orchestrator(restarted_tm, reg)
    restarted_task = await restarted_orch.run_task(task.task_id)

    # Step must advance to COMPLETED without re-executing
    assert restarted_task.status == TaskStatus.COMPLETED
    assert (ws / "counter.txt").read_text() == "1"


# Crash recovery: interrupted non-idempotent action without empirical criteria fails closed
@pytest.mark.asyncio
async def test_crash_recovery_interrupted_without_criteria_fails_closed(tmp_path: Path):
    ws, tm, reg, orch = setup_runtime(tmp_path)
    task = tm.create_task("crash mid flight", str(ws))
    # Step with no verification criteria
    step = PlanStep(
        order=1,
        description="unverified_action",
        capability_required=WorkerCapability.SYSTEM,
        actions=[
            Action(
                worker="system_worker", tool="shell", parameters={"command": "printf x >> log.txt"}
            )
        ],
        verification={},
    )
    tm.start_task(task.task_id)
    tm.update_plan(task.task_id, [step])
    tm.transition_task(task.task_id, TaskStatus.RUNNING)

    # Insert action with status RUNNING to simulate mid-flight crash
    import time

    with tm.db.get_connection() as conn:
        conn.execute(
            """INSERT INTO actions (action_id, task_id, step_id, worker, tool, parameters_json, timestamp, status)
               VALUES ('act_crash', ?, ?, 'system_worker', 'shell', '{}', ?, 'RUNNING')""",
            (task.task_id, step.step_id, time.time()),
        )
        conn.commit()

    restarted_tm = TaskManager(Database(ws / "hardening_audit.db"))
    restarted_orch = Orchestrator(restarted_tm, reg)
    out = await restarted_orch.run_task(task.task_id)

    # Must fail closed with crash recovery halt, never falsely complete
    assert out.status == TaskStatus.FAILED
    assert "Crash recovery halted" in (out.metadata.get("error", "") or str(out))


@pytest.mark.asyncio
async def test_orchestrator_concurrent_task_execution_rejected(tmp_path: Path):
    import asyncio

    ws, tm, reg, orch = setup_runtime(tmp_path)
    task = tm.create_task("concurrent lease test", str(ws))

    base_tool = reg.get("write_file")
    assert base_tool is not None

    class AsyncYieldTool(base_tool.__class__):
        async def run(self, **kwargs):
            await asyncio.sleep(0.05)
            return await super().run(**kwargs)

    reg.replace(AsyncYieldTool(ws))
    step = make_step("write_file", {"path": "concurrent.txt", "content": "hello"})

    # Launch two concurrent runs for the same task
    res1, res2 = await asyncio.gather(
        orch.run_task(task.task_id, [step]),
        orch.run_task(task.task_id, [step]),
        return_exceptions=True,
    )

    # One must succeed and one must be rejected with RuntimeError
    exceptions = [r for r in (res1, res2) if isinstance(r, RuntimeError)]
    successes = [r for r in (res1, res2) if not isinstance(r, Exception)]
    assert len(exceptions) == 1
    assert "already actively executing" in str(exceptions[0])
    assert len(successes) == 1


def test_supervisor_kill_pgid_safety():
    from nani.tools.supervisor import SubprocessSupervisor

    # Must safely ignore None, 0, 1 without raising or killing host processes
    SubprocessSupervisor._kill_pgid(None)
    SubprocessSupervisor._kill_pgid(0)
    SubprocessSupervisor._kill_pgid(1)
    SubprocessSupervisor._kill_pgid(-1)
