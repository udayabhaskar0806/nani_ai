"""Unit tests for TaskManager lifecycle enforcement, illegal transitions, and persistence."""

from pathlib import Path

import pytest

from nani.core.task import (
    InvalidTaskTransition,
    PlanStep,
    RiskLevel,
    StepStatus,
    TaskStatus,
    WorkerCapability,
)
from nani.core.task_manager import TaskManager
from nani.memory.database import Database


@pytest.fixture
def tm(tmp_path: Path) -> TaskManager:
    db = Database(tmp_path / "tm_test.db")
    return TaskManager(db=db)


def test_task_manager_create_and_get(tm: TaskManager, tmp_path: Path):
    task = tm.create_task(
        goal="Build binary",
        workspace_path=str(tmp_path),
        risk_level=RiskLevel.MEDIUM,
        metadata={"priority": 1},
    )
    assert task.status == TaskStatus.CREATED
    assert task.original_goal == "Build binary"
    assert task.risk_level == RiskLevel.MEDIUM

    fetched = tm.get_task(task.task_id)
    assert fetched is not None
    assert fetched.task_id == task.task_id
    assert fetched.original_goal == "Build binary"
    assert fetched.metadata["priority"] == 1


def test_task_manager_legal_lifecycle_transitions(tm: TaskManager):
    task = tm.create_task(goal="Lifecycle demo")
    assert task.status == TaskStatus.CREATED

    # CREATED -> PLANNING
    task = tm.start_task(task.task_id)
    assert task.status == TaskStatus.PLANNING

    # PLANNING -> RUNNING
    task = tm.transition_task(task.task_id, TaskStatus.RUNNING, reason="Plan ready")
    assert task.status == TaskStatus.RUNNING

    # RUNNING -> VERIFYING
    task = tm.transition_task(task.task_id, TaskStatus.VERIFYING, reason="Execution complete")
    assert task.status == TaskStatus.VERIFYING

    # VERIFYING -> COMPLETED
    task = tm.complete_task(task.task_id)
    assert task.status == TaskStatus.COMPLETED


def test_task_manager_additional_legal_paths(tm: TaskManager):
    # RUNNING -> WAITING -> RUNNING
    t1 = tm.create_task(goal="Wait demo")
    t1 = tm.start_task(t1.task_id)
    t1 = tm.transition_task(t1.task_id, TaskStatus.RUNNING)
    t1 = tm.transition_task(t1.task_id, TaskStatus.WAITING, reason="Need approval")
    assert t1.status == TaskStatus.WAITING
    t1 = tm.transition_task(t1.task_id, TaskStatus.RUNNING, reason="Approved")
    assert t1.status == TaskStatus.RUNNING

    # RUNNING -> RECOVERY -> RUNNING
    t1 = tm.transition_task(t1.task_id, TaskStatus.RECOVERY, reason="Step error")
    assert t1.status == TaskStatus.RECOVERY
    t1 = tm.transition_task(t1.task_id, TaskStatus.RUNNING, reason="Retry step")
    assert t1.status == TaskStatus.RUNNING

    # RUNNING -> PAUSED -> RUNNING
    t1 = tm.pause_task(t1.task_id)
    assert t1.status == TaskStatus.PAUSED
    t1 = tm.resume_task(t1.task_id)
    assert t1.status == TaskStatus.RUNNING


def test_task_manager_illegal_transitions_rejected(tm: TaskManager):
    task = tm.create_task(goal="Illegal transitions test")

    # CREATED -> RUNNING is illegal (must go through PLANNING)
    with pytest.raises(InvalidTaskTransition, match="cannot transition from CREATED to RUNNING"):
        tm.transition_task(task.task_id, TaskStatus.RUNNING)

    # Move to COMPLETED
    task = tm.start_task(task.task_id)
    task = tm.transition_task(task.task_id, TaskStatus.RUNNING)
    task = tm.transition_task(task.task_id, TaskStatus.VERIFYING)
    task = tm.complete_task(task.task_id)
    assert task.status == TaskStatus.COMPLETED

    # COMPLETED -> RUNNING must raise InvalidTaskTransition
    with pytest.raises(InvalidTaskTransition, match="cannot transition from COMPLETED to RUNNING"):
        tm.transition_task(task.task_id, TaskStatus.RUNNING)

    # COMPLETED -> FAILED must raise InvalidTaskTransition
    with pytest.raises(InvalidTaskTransition):
        tm.fail_task(task.task_id)


def test_task_cancellation_from_active_states(tm: TaskManager):
    # From CREATED
    t1 = tm.create_task(goal="Cancel 1")
    t1 = tm.cancel_task(t1.task_id)
    assert t1.status == TaskStatus.CANCELLED

    # Cancelled task cannot transition to anything
    with pytest.raises(InvalidTaskTransition):
        tm.start_task(t1.task_id)


def test_task_persistence_across_manager_reinstantiation(tmp_path: Path):
    db_file = tmp_path / "persist_crash.db"
    db1 = Database(db_file)
    tm1 = TaskManager(db=db1)

    task = tm1.create_task(goal="Survive process termination", workspace_path=str(tmp_path))
    task = tm1.start_task(task.task_id)
    task = tm1.transition_task(task.task_id, TaskStatus.RUNNING)

    # Attach plan steps
    step1 = PlanStep(
        order=1,
        description="Compile binary",
        capability_required=WorkerCapability.CODING,
        status=StepStatus.COMPLETED,
        verification={"type": "exit_code", "expected": 0},
        retry_count=1,
    )
    step2 = PlanStep(
        order=2,
        description="Run binary",
        capability_required=WorkerCapability.SYSTEM,
        status=StepStatus.PENDING,
    )
    tm1.update_plan(task.task_id, [step1, step2])
    tm1.set_current_step_index(task.task_id, 1)
    tm1.pause_task(task.task_id)

    # Simulate process termination: destroy tm1 and db1
    del tm1
    del db1

    # Restart NANI with fresh Database and TaskManager
    db2 = Database(db_file)
    tm2 = TaskManager(db=db2)

    restored = tm2.restore_task(task.task_id)
    assert restored is not None
    assert restored.status == TaskStatus.PAUSED
    assert restored.original_goal == "Survive process termination"
    assert restored.current_step_index == 1
    assert len(restored.plan) == 2
    assert restored.plan[0].status == StepStatus.COMPLETED
    assert restored.plan[0].retry_count == 1
    assert restored.plan[0].verification["expected"] == 0
    assert restored.plan[1].status == StepStatus.PENDING


def test_task_transition_records_journal_entries(tm: TaskManager):
    task = tm.create_task(goal="Transition journal test")
    tm.start_task(task.task_id)

    with tm.db.get_connection() as conn:
        cur = conn.execute(
            "SELECT * FROM journal_entries WHERE task_id = ? AND entry_type = 'TRANSITION' ORDER BY timestamp ASC",
            (task.task_id,),
        )
        rows = cur.fetchall()
        assert len(rows) >= 1
        assert rows[-1]["status"] == TaskStatus.PLANNING.value
