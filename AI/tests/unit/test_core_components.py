"""Unit tests for Planner, Verifier, RecoveryManager, and ToolRegistry execution gates."""

from pathlib import Path
from typing import Any

import pytest

from nani.core.planner import Planner
from nani.core.recovery import RecoveryManager
from nani.core.task import (
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
from nani.tools.registry import BaseTool, ToolRegistry
from nani.tools.result import ToolResult

# --- Planner Tests ---


def test_planner_deterministic_c_project():
    planner = Planner()
    steps = planner.plan(goal="Create a small C project")
    assert len(steps) == 4
    assert steps[0].capability_required == WorkerCapability.SYSTEM
    assert steps[1].capability_required == WorkerCapability.CODING
    assert steps[2].capability_required == WorkerCapability.CODING
    assert steps[3].capability_required == WorkerCapability.CODING
    assert "NANI_PHASE1_OK" in steps[1].actions[0].parameters["content"]


def test_planner_predefined_steps():
    planner = Planner()
    custom_step = PlanStep(
        order=1,
        description="Custom action",
        capability_required=WorkerCapability.SYSTEM,
    )
    steps = planner.plan(goal="Custom goal", predefined_steps=[custom_step])
    assert len(steps) == 1
    assert steps[0].description == "Custom action"


# --- Verifier Tests ---


def test_verifier_exit_code_and_tool_success():
    verifier = Verifier()
    step = PlanStep(
        order=1,
        description="Run test",
        capability_required=WorkerCapability.SYSTEM,
        verification={"type": "exit_code", "expected": 0},
    )

    res_ok = ToolResult.ok(stdout="Passed", exit_code=0)
    v_ok = verifier.verify_step(step, res_ok)
    assert v_ok.verified is True

    res_fail = ToolResult.fail(error="Crash", exit_code=1)
    v_fail = verifier.verify_step(step, res_fail)
    assert v_fail.verified is False
    assert any("Exit code mismatch" in r for r in v_fail.failure_reasons)


def test_verifier_file_content_and_existence(tmp_path: Path):
    verifier = Verifier()
    file_path = tmp_path / "hello.txt"
    file_path.write_text("Exact expected content")

    step_ok = PlanStep(
        order=1,
        description="Verify hello.txt",
        capability_required=WorkerCapability.CODING,
        verification={
            "type": "file_content",
            "path": "hello.txt",
            "expected_content": "Exact expected content",
        },
    )
    v_ok = verifier.verify_step(step_ok, workspace_path=tmp_path)
    assert v_ok.verified is True

    step_mismatch = PlanStep(
        order=2,
        description="Verify hello.txt mismatch",
        capability_required=WorkerCapability.CODING,
        verification={
            "type": "file_content",
            "path": "hello.txt",
            "expected_content": "Different text",
        },
    )
    v_mismatch = verifier.verify_step(step_mismatch, workspace_path=tmp_path)
    assert v_mismatch.verified is False


# --- Recovery Tests ---


def test_recovery_retry_limit_enforcement(tmp_path: Path):
    db = Database(tmp_path / "recovery_test.db")
    tm = TaskManager(db=db)
    recovery = RecoveryManager()

    task = tm.create_task(goal="Flaky compile")
    task = tm.start_task(task.task_id)
    task = tm.transition_task(task.task_id, TaskStatus.RUNNING)

    step = PlanStep(
        order=1,
        description="Compile",
        capability_required=WorkerCapability.CODING,
        max_retries=2,
        retry_count=0,
    )
    tm.update_plan(task.task_id, [step])

    # Retry 1
    task, should_retry = recovery.handle_step_failure(task, step, "Transient error 1", tm)
    assert should_retry is True
    assert step.retry_count == 1
    assert task.status == TaskStatus.RUNNING

    # Retry 2
    task, should_retry = recovery.handle_step_failure(task, step, "Transient error 2", tm)
    assert should_retry is True
    assert step.retry_count == 2
    assert task.status == TaskStatus.RUNNING

    # Retry 3: max_retries reached -> FAILED
    task, should_retry = recovery.handle_step_failure(task, step, "Transient error 3", tm)
    assert should_retry is False
    assert task.status == TaskStatus.FAILED
    assert step.status == StepStatus.FAILED


# --- ToolRegistry Execution Gate Tests ---


class DummySafeTool(BaseTool):
    @property
    def name(self) -> str:
        return "safe_echo"

    @property
    def description(self) -> str:
        return "Safe dummy tool"

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.LOW

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"msg": {"type": "string"}},
            "required": ["msg"],
        }

    async def run(self, **kwargs: Any) -> ToolResult:
        return ToolResult.ok(stdout=str(kwargs.get("msg", "")))


@pytest.mark.asyncio
async def test_tool_registry_execution_and_journaling(tmp_path: Path):
    db = Database(tmp_path / "gate_test.db")
    journal = ActionJournal(db)
    tm = TaskManager(db=db, journal=journal)
    registry = ToolRegistry(journal=journal)
    registry.register(DummySafeTool())

    task = tm.create_task(goal="Execute gate")

    # 1. Parameter validation failure
    res_val = await registry.execute("safe_echo", {}, task_id=task.task_id)
    assert res_val.success is False
    assert "Missing required parameter" in res_val.error

    # 2. Successful execution with journal entries
    res_ok = await registry.execute("safe_echo", {"msg": "Hello NANI"}, task_id=task.task_id)
    assert res_ok.success is True
    assert res_ok.stdout == "Hello NANI"

    # Verify journal recorded start and result
    hist = journal.reconstruct_task_history(task.task_id)
    assert len(hist["actions"]) == 1
    assert hist["actions"][0]["tool"] == "safe_echo"
    assert hist["actions"][0]["status"] == "SUCCESS"


@pytest.mark.asyncio
async def test_tool_registry_high_risk_blocks_and_requests_approval(tmp_path: Path):
    db = Database(tmp_path / "block_test.db")
    journal = ActionJournal(db)
    tm = TaskManager(db=db, journal=journal)
    registry = ToolRegistry(journal=journal)

    class HighRiskTool(BaseTool):
        @property
        def name(self) -> str:
            return "delete_directory"

        @property
        def description(self) -> str:
            return "High risk tool"

        @property
        def risk_level(self) -> RiskLevel:
            return RiskLevel.HIGH

        async def run(self, **kwargs: Any) -> ToolResult:
            return ToolResult.ok()

    registry.register(HighRiskTool())
    task = tm.create_task(goal="Block high risk")

    res = await registry.execute("delete_directory", {"target": "all"}, task_id=task.task_id)
    assert res.success is False
    assert res.metadata["approval_required"] is True
    assert "HIGH" in res.error

    hist = journal.reconstruct_task_history(task.task_id)
    assert len(hist["approvals"]) == 1
    assert hist["approvals"][0]["risk_level"] == "HIGH"
    assert hist["actions"][0]["status"] == "BLOCKED"
