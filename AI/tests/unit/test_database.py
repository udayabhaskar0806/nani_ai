"""Unit tests for Phase 0 SQLite schema, persistence, and action journal."""

import time
from pathlib import Path

import pytest

from nani.memory.database import Database


@pytest.fixture
def test_db(tmp_path: Path) -> Database:
    db_file = tmp_path / "test_nani.db"
    return Database(db_file)


def test_schema_initialization(test_db: Database):
    version = test_db.get_schema_version()
    assert version >= 1

    with test_db.get_connection() as conn:
        # Verify WAL mode
        cur = conn.execute("PRAGMA journal_mode;")
        row = cur.fetchone()
        assert row[0].upper() == "WAL"

        # Verify tables exist
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [r[0] for r in cur.fetchall()]
        assert "tasks" in tables
        assert "plan_steps" in tables
        assert "actions" in tables
        assert "observations" in tables
        assert "approvals" in tables
        assert "projects" in tables


def test_task_insertion_and_retrieval(test_db: Database):
    with test_db.get_connection() as conn:
        task_id = "task-test-123"
        conn.execute(
            """INSERT INTO tasks (task_id, original_goal, interpreted_goal, workspace_path, status, risk_level, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                task_id,
                "Fix kernel panic",
                "Debug null pointer in module",
                "/tmp",
                "RUNNING",
                "MEDIUM",
                time.time(),
                time.time(),
            ),
        )
        conn.commit()

        cur = conn.execute(
            "SELECT task_id, original_goal, status FROM tasks WHERE task_id = ?", (task_id,)
        )
        row = cur.fetchone()
        assert row is not None
        assert row["task_id"] == task_id
        assert row["original_goal"] == "Fix kernel panic"
        assert row["status"] == "RUNNING"


def test_action_journal_insertion(test_db: Database):
    with test_db.get_connection() as conn:
        task_id = "task-journal-456"
        conn.execute(
            """INSERT INTO tasks (task_id, original_goal, workspace_path, status, risk_level, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (task_id, "Inspect hardware", "/tmp", "RUNNING", "LOW", time.time(), time.time()),
        )

        step_id = "step-1"
        conn.execute(
            """INSERT INTO plan_steps (step_id, task_id, step_order, description, capability_required, status, risk_level)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (step_id, task_id, 1, "Run pactl volume query", "system", "IN_PROGRESS", "LOW"),
        )

        action_id = "act-999"
        conn.execute(
            """INSERT INTO actions (action_id, task_id, step_id, worker, tool, parameters_json, timestamp, duration_ms, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                action_id,
                task_id,
                step_id,
                "system_worker",
                "pactl_get",
                '{"device": "default"}',
                time.time(),
                45,
                "SUCCESS",
            ),
        )

        obs_id = "obs-888"
        conn.execute(
            """INSERT INTO observations (observation_id, action_id, step_id, timestamp, source, content)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (obs_id, action_id, step_id, time.time(), "stdout", "Volume: 65%"),
        )
        conn.commit()

        cur = conn.execute(
            "SELECT worker, tool, status FROM actions WHERE action_id = ?", (action_id,)
        )
        row = cur.fetchone()
        assert row is not None
        assert row["worker"] == "system_worker"
        assert row["status"] == "SUCCESS"

        cur = conn.execute("SELECT content FROM observations WHERE action_id = ?", (action_id,))
        obs_row = cur.fetchone()
        assert obs_row is not None
        assert obs_row["content"] == "Volume: 65%"
