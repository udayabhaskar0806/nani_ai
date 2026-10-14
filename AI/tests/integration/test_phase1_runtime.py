"""N.A.N.I. V2 — Phase 1 Core Autonomous Runtime Integration Tests
End-to-end deterministic runtime validation without AI models.
"""

from pathlib import Path

import pytest

from nani.core.orchestrator import Orchestrator
from nani.core.planner import Planner
from nani.core.recovery import RecoveryManager
from nani.core.router import CapabilityRouter
from nani.core.task import (
    Action,
    PlanStep,
    RiskLevel,
    StepStatus,
    TaskStatus,
    WorkerCapability,
)
from nani.core.task_manager import TaskManager
from nani.core.verifier import Verifier
from nani.memory.database import Database
from nani.memory.journal import ActionJournal
from nani.tools.filesystem import register_filesystem_tools
from nani.tools.git import register_git_tools
from nani.tools.process import register_process_tools
from nani.tools.registry import BaseTool, ToolRegistry
from nani.tools.result import ToolResult
from nani.tools.shell import register_shell_tools


def setup_test_runtime(
    workspace_path: Path, db_path: Path
) -> tuple[TaskManager, ToolRegistry, Orchestrator, ActionJournal]:
    """Helper to assemble a clean Phase 1 runtime."""
    db = Database(db_path)
    journal = ActionJournal(db)
    tm = TaskManager(db=db, journal=journal)

    registry = ToolRegistry(journal=journal)
    register_filesystem_tools(registry, workspace_path=workspace_path)
    register_shell_tools(registry, workspace_path=workspace_path)
    register_process_tools(registry, workspace_path=workspace_path)
    register_git_tools(registry, workspace_path=workspace_path)

    orchestrator = Orchestrator(
        task_manager=tm,
        tool_registry=registry,
        planner=Planner(),
        router=CapabilityRouter(),
        verifier=Verifier(),
        recovery=RecoveryManager(),
        journal=journal,
    )
    return tm, registry, orchestrator, journal


@pytest.mark.asyncio
async def test_phase1_c_project_success(tmp_path: Path):
    """End-to-End autonomous C project build and execution (Section 18).

    CREATED -> PLANNING -> RUNNING -> write_file -> gcc -> ./hello -> VERIFYING -> COMPLETED.
    """
    ws = tmp_path / "c_workspace"
    ws.mkdir()
    db_file = tmp_path / "c_project.db"

    tm, registry, orchestrator, journal = setup_test_runtime(ws, db_file)

    task = tm.create_task(goal="Create a small C project", workspace_path=str(ws))
    assert task.status == TaskStatus.CREATED

    completed_task = await orchestrator.run_task(task.task_id)

    # 1. Verify terminal status
    assert completed_task.status == TaskStatus.COMPLETED
    assert completed_task.current_step_index == len(completed_task.plan)

    # 2. Verify all steps completed
    for step in completed_task.plan:
        assert step.status == StepStatus.COMPLETED

    # 3. Verify concrete filesystem artifacts
    hello_c = ws / "hello.c"
    hello_bin = ws / "hello"
    assert hello_c.is_file()
    assert hello_bin.is_file()
    assert "NANI_PHASE1_OK" in hello_c.read_text()


@pytest.mark.asyncio
async def test_phase1_compile_failure(tmp_path: Path):
    """Failure acceptance test with broken C syntax (Section 19).

    compile fails -> observation recorded -> RECOVERY -> retries exhausted -> FAILED.
    """
    ws = tmp_path / "broken_c_ws"
    ws.mkdir()
    db_file = tmp_path / "broken_c.db"

    tm, registry, orchestrator, journal = setup_test_runtime(ws, db_file)

    task = tm.create_task(
        goal="Create a small C project",
        workspace_path=str(ws),
        metadata={"broken_syntax": True},
    )

    failed_task = await orchestrator.run_task(task.task_id)

    # Must cleanly reach FAILED state without infinite loop
    assert failed_task.status == TaskStatus.FAILED

    # Step 3 (gcc compile) must be marked FAILED with max retries reached
    compile_step = failed_task.plan[2]
    assert compile_step.status == StepStatus.FAILED
    assert compile_step.retry_count == compile_step.max_retries
    assert compile_step.error is not None


@pytest.mark.asyncio
async def test_phase1_pause_resume(tmp_path: Path):
    """Pause during multi-step execution and resume to completion (Section 17 & 20)."""
    ws = tmp_path / "pause_ws"
    ws.mkdir()
    db_file = tmp_path / "pause.db"

    tm, registry, orchestrator, journal = setup_test_runtime(ws, db_file)

    step1 = PlanStep(
        order=1,
        description="Create file 1",
        capability_required=WorkerCapability.CODING,
        actions=[
            Action(
                worker="coding_worker",
                tool="write_file",
                parameters={"path": "f1.txt", "content": "File 1 content"},
            )
        ],
        verification={"type": "file_exists", "path": "f1.txt"},
    )
    step2 = PlanStep(
        order=2,
        description="Create file 2",
        capability_required=WorkerCapability.CODING,
        actions=[
            Action(
                worker="coding_worker",
                tool="write_file",
                parameters={"path": "f2.txt", "content": "File 2 content"},
            )
        ],
        verification={"type": "file_exists", "path": "f2.txt"},
    )

    task = tm.create_task(goal="Pause resume demo", workspace_path=str(ws))

    # Request pause before run begins
    orchestrator.request_pause()
    paused_task = await orchestrator.run_task(task.task_id, predefined_steps=[step1, step2])
    assert paused_task.status == TaskStatus.PAUSED

    # Resume execution to completion
    resumed_task = await orchestrator.run_task(paused_task.task_id)
    assert resumed_task.status == TaskStatus.COMPLETED
    assert (ws / "f1.txt").is_file()
    assert (ws / "f2.txt").is_file()


@pytest.mark.asyncio
async def test_phase1_crash_resume(tmp_path: Path):
    """Process crash simulation and resumption from persisted step (Section 20)."""
    ws = tmp_path / "crash_ws"
    ws.mkdir()
    db_file = tmp_path / "crash.db"

    # Step 1: Create first runtime and execute only Step 1
    tm1, registry1, orchestrator1, journal1 = setup_test_runtime(ws, db_file)

    step1 = PlanStep(
        order=1,
        description="Create initial artifact",
        capability_required=WorkerCapability.CODING,
        actions=[
            Action(
                worker="coding_worker",
                tool="write_file",
                parameters={"path": "step1.txt", "content": "Step 1 done"},
            )
        ],
        verification={"type": "file_exists", "path": "step1.txt"},
    )
    step2 = PlanStep(
        order=2,
        description="Create second artifact",
        capability_required=WorkerCapability.CODING,
        actions=[
            Action(
                worker="coding_worker",
                tool="write_file",
                parameters={"path": "step2.txt", "content": "Step 2 done"},
            )
        ],
        verification={"type": "file_exists", "path": "step2.txt"},
    )

    task = tm1.create_task(goal="Crash resilience test", workspace_path=str(ws))
    task = tm1.start_task(task.task_id)
    task = tm1.update_plan(task.task_id, [step1, step2])
    task = tm1.transition_task(task.task_id, TaskStatus.RUNNING)

    # Execute step 1 manually through registry and verify
    await registry1.execute(
        name="write_file",
        parameters={"path": "step1.txt", "content": "Step 1 done", "workspace_path": str(ws)},
        task_id=task.task_id,
        step_id=step1.step_id,
    )
    task.plan[0].status = StepStatus.COMPLETED
    task.current_step_index = 1
    tm1.persist_task(task)

    # SIMULATE HARD PROCESS CRASH: delete all in-memory references
    del tm1
    del registry1
    del orchestrator1
    del journal1

    # Step 2: Boot fresh runtime instance from SQLite
    tm2, registry2, orchestrator2, journal2 = setup_test_runtime(ws, db_file)

    # Step 1 must already be COMPLETED in database
    reloaded_task = tm2.get_task(task.task_id)
    assert reloaded_task is not None
    assert reloaded_task.current_step_index == 1
    assert reloaded_task.plan[0].status == StepStatus.COMPLETED

    # Resume execution
    final_task = await orchestrator2.run_task(reloaded_task.task_id)
    assert final_task.status == TaskStatus.COMPLETED
    assert (ws / "step1.txt").is_file()
    assert (ws / "step2.txt").is_file()


@pytest.mark.asyncio
async def test_phase1_security_waiting(tmp_path: Path):
    """High-risk action blocked by SecurityPolicy -> Task enters WAITING (Section 21)."""
    ws = tmp_path / "security_ws"
    ws.mkdir()
    db_file = tmp_path / "security.db"

    tm, registry, orchestrator, journal = setup_test_runtime(ws, db_file)

    # Use a dummy harmless command classified/mocked as HIGH risk
    class HighRiskTestTool(BaseTool):
        @property
        def name(self) -> str:
            return "high_risk_gate_op"

        @property
        def description(self) -> str:
            return "Harmless test tool declared as HIGH risk"

        @property
        def risk_level(self) -> RiskLevel:
            return RiskLevel.HIGH

        async def run(self, **kwargs) -> ToolResult:
            raise RuntimeError("CRITICAL ERROR: High risk tool should never have executed!")

    registry.register(HighRiskTestTool())

    high_risk_step = PlanStep(
        order=1,
        description="Execute high-risk gated operation",
        capability_required=WorkerCapability.SYSTEM,
        actions=[
            Action(
                worker="system_worker",
                tool="high_risk_gate_op",
                parameters={"param": "value"},
            )
        ],
    )

    task = tm.create_task(goal="Security escalation test", workspace_path=str(ws))
    waiting_task = await orchestrator.run_task(task.task_id, predefined_steps=[high_risk_step])

    # Task must enter WAITING
    assert waiting_task.status == TaskStatus.WAITING

    # Approval request must be recorded
    history = journal.reconstruct_task_history(task.task_id)
    assert len(history["approvals"]) == 1
    assert history["approvals"][0]["risk_level"] == "HIGH"
    assert history["approvals"][0]["status"] == "PENDING"


@pytest.mark.asyncio
async def test_phase1_journal_reconstruction(tmp_path: Path):
    """Episodic history reconstruction from SQLite (Section 22)."""
    ws = tmp_path / "journal_recon_ws"
    ws.mkdir()
    db_file = tmp_path / "journal_recon.db"

    tm, registry, orchestrator, journal = setup_test_runtime(ws, db_file)

    task = tm.create_task(goal="Create a small C project", workspace_path=str(ws))
    await orchestrator.run_task(task.task_id)

    # Reconstruct from SQLite database
    history = journal.reconstruct_task_history(task.task_id)

    assert history["goal"] == "Create a small C project"
    assert history["final_status"] == "COMPLETED"
    assert len(history["plan"]) == 4
    assert len(history["state_transitions"]) >= 4
    assert len(history["actions"]) >= 4
    assert len(history["observations"]) >= 4

    # Verify tools called in order
    assert "list_directory" in history["tools_called"]
    assert "write_file" in history["tools_called"]
    assert "shell" in history["tools_called"]

    # Verify exit codes and durations
    assert 0 in history["exit_codes"]
    assert history["total_duration_ms"] >= 0
