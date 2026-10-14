"""Unit tests for ActionJournal recording, secret sanitization, and reconstruction."""

from pathlib import Path

import pytest

from nani.core.task import ActionStatus, RiskLevel, TaskStatus
from nani.core.task_manager import TaskManager
from nani.memory.database import Database
from nani.memory.journal import ActionJournal


@pytest.fixture
def journal_and_tm(tmp_path: Path) -> tuple[ActionJournal, TaskManager]:
    db = Database(tmp_path / "journal_test.db")
    journal = ActionJournal(db)
    tm = TaskManager(db=db, journal=journal)
    return journal, tm


def test_action_journal_records_start_and_result(journal_and_tm: tuple[ActionJournal, TaskManager]):
    journal, tm = journal_and_tm
    task = tm.create_task(goal="Journal test")

    act_id = journal.record_action_start(
        task_id=task.task_id,
        step_id="step-1",
        worker="coding_worker",
        tool="write_file",
        parameters={"path": "hello.c", "api_key": "AIzaSySecretApiKey12345678901234567890"},
    )
    assert act_id is not None

    journal.record_action_result(
        action_id=act_id,
        status=ActionStatus.SUCCESS,
        duration_ms=42,
        result={"bytes_written": 128},
        error=None,
    )

    history = journal.reconstruct_task_history(task.task_id)
    assert len(history["actions"]) == 1
    act = history["actions"][0]
    assert act["action_id"] == act_id
    assert act["status"] == "SUCCESS"
    assert act["duration_ms"] == 42
    # Verify API key credential was redacted
    assert "AIzaSySecretApiKey" not in str(act["parameters"])
    assert "[REDACTED]" in str(act["parameters"])


def test_action_journal_records_observation_and_transition(
    journal_and_tm: tuple[ActionJournal, TaskManager],
):
    journal, tm = journal_and_tm
    task = tm.create_task(goal="Observation test")

    journal.record_transition(
        task_id=task.task_id,
        from_status=TaskStatus.CREATED,
        to_status=TaskStatus.PLANNING,
        reason="Started planner",
    )

    obs_id = journal.record_observation(
        source="stdout",
        content="Compilation output: password=supersecretpass123",
        task_id=task.task_id,
        metadata={"compiler": "gcc"},
    )
    assert obs_id is not None

    history = journal.reconstruct_task_history(task.task_id)
    assert len(history["state_transitions"]) >= 2
    assert len(history["observations"]) == 1
    obs = history["observations"][0]
    assert obs["source"] == "stdout"
    # Verify password redaction
    assert "supersecretpass123" not in obs["content"]
    assert "[REDACTED]" in obs["content"]


def test_action_journal_records_approval_request(journal_and_tm: tuple[ActionJournal, TaskManager]):
    journal, tm = journal_and_tm
    task = tm.create_task(goal="Approval test")

    app_id = journal.record_approval_request(
        task_id=task.task_id,
        step_id="step-high",
        action_description="Execute dangerous shell command",
        risk_level=RiskLevel.HIGH,
    )
    assert app_id is not None

    history = journal.reconstruct_task_history(task.task_id)
    assert len(history["approvals"]) == 1
    assert history["approvals"][0]["risk_level"] == "HIGH"
    assert history["approvals"][0]["status"] == "PENDING"
