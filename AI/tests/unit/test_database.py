"""Hardened unit tests for SQLite schema, query indexes, foreign-key cascades, and transactional migrations."""

import sqlite3
import time
from pathlib import Path

import pytest

from nani.memory.database import Database, MigrationError


@pytest.fixture
def test_db(tmp_path: Path) -> Database:
    db_file = tmp_path / "test_nani_hardened.db"
    return Database(db_file)


def test_schema_version_and_wal_mode(test_db: Database):
    version = test_db.get_schema_version()
    assert version >= 1

    with test_db.get_connection() as conn:
        cur = conn.execute("PRAGMA journal_mode;")
        assert cur.fetchone()[0].upper() == "WAL"

        cur = conn.execute("PRAGMA foreign_keys;")
        assert cur.fetchone()[0] == 1


def test_query_indexes_exist(test_db: Database):
    with test_db.get_connection() as conn:
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='index';")
        indexes = [r[0] for r in cur.fetchall()]
        assert "idx_plan_steps_task_id" in indexes
        assert "idx_actions_task_id" in indexes
        assert "idx_actions_step_id" in indexes
        assert "idx_observations_action_id" in indexes
        assert "idx_observations_step_id" in indexes
        assert "idx_approvals_task_id" in indexes
        assert "idx_episodic_memory_task_id" in indexes


def test_foreign_key_violation_rejected(test_db: Database):
    with test_db.get_connection() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            # Inserting a step pointing to a non-existent task must fail
            conn.execute(
                """INSERT INTO plan_steps (step_id, task_id, step_order, description, capability_required, status, risk_level)
                   VALUES ('step-orphan', 'non-existent-task-id', 1, 'Invalid step', 'SYSTEM', 'PENDING', 'LOW')"""
            )


def test_task_cascade_deletion(test_db: Database):
    task_id = "task-cascade-root"
    step_id = "step-cascade-1"
    action_id = "act-cascade-1"

    with test_db.get_connection() as conn:
        # Insert parent task
        conn.execute(
            """INSERT INTO tasks (task_id, original_goal, workspace_path, status, risk_level, created_at, updated_at)
               VALUES (?, 'Root Task', '/tmp', 'RUNNING', 'LOW', ?, ?)""",
            (task_id, time.time(), time.time()),
        )
        # Insert child step
        conn.execute(
            """INSERT INTO plan_steps (step_id, task_id, step_order, description, capability_required, status, risk_level)
               VALUES (?, ?, 1, 'Child step', 'CODING', 'RUNNING', 'LOW')""",
            (step_id, task_id),
        )
        # Insert child action
        conn.execute(
            """INSERT INTO actions (action_id, task_id, step_id, worker, tool, parameters_json, timestamp, status)
               VALUES (?, ?, ?, 'coding_worker', 'read_file', '{}', ?, 'SUCCESS')""",
            (action_id, task_id, step_id, time.time()),
        )
        conn.commit()

        # Delete parent task
        conn.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
        conn.commit()

        # Child step and child action must be automatically cascade deleted
        cur_step = conn.execute("SELECT step_id FROM plan_steps WHERE step_id = ?", (step_id,))
        assert cur_step.fetchone() is None

        cur_act = conn.execute("SELECT action_id FROM actions WHERE action_id = ?", (action_id,))
        assert cur_act.fetchone() is None


def test_plan_step_cascade_deletion(test_db: Database):
    task_id = "task-parent-2"
    step_id = "step-child-2"
    action_id = "act-grandchild-2"

    with test_db.get_connection() as conn:
        conn.execute(
            """INSERT INTO tasks (task_id, original_goal, workspace_path, status, risk_level, created_at, updated_at)
               VALUES (?, 'Parent Task', '/tmp', 'RUNNING', 'LOW', ?, ?)""",
            (task_id, time.time(), time.time()),
        )
        conn.execute(
            """INSERT INTO plan_steps (step_id, task_id, step_order, description, capability_required, status, risk_level)
               VALUES (?, ?, 1, 'Child step', 'SYSTEM', 'RUNNING', 'LOW')""",
            (step_id, task_id),
        )
        conn.execute(
            """INSERT INTO actions (action_id, task_id, step_id, worker, tool, parameters_json, timestamp, status)
               VALUES (?, ?, ?, 'system_worker', 'ls', '{}', ?, 'SUCCESS')""",
            (action_id, task_id, step_id, time.time()),
        )
        conn.commit()

        # Deleting plan step deletes action
        conn.execute("DELETE FROM plan_steps WHERE step_id = ?", (step_id,))
        conn.commit()

        cur_act = conn.execute("SELECT action_id FROM actions WHERE action_id = ?", (action_id,))
        assert cur_act.fetchone() is None

        # Parent task remains intact
        cur_task = conn.execute("SELECT task_id FROM tasks WHERE task_id = ?", (task_id,))
        assert cur_task.fetchone() is not None


def test_database_close_and_reopen_persists_data(tmp_path: Path):
    db_file = tmp_path / "persistent_test.db"
    task_id = "task-persist-99"

    # 1. Create and write
    db1 = Database(db_file)
    with db1.get_connection() as conn:
        conn.execute(
            """INSERT INTO tasks (task_id, original_goal, workspace_path, status, risk_level, created_at, updated_at)
               VALUES (?, 'Persist Goal', '/tmp', 'CREATED', 'LOW', ?, ?)""",
            (task_id, time.time(), time.time()),
        )
        conn.commit()

    # 2. Reopen fresh Database instance
    db2 = Database(db_file)
    with db2.get_connection() as conn:
        cur = conn.execute("SELECT original_goal FROM tasks WHERE task_id = ?", (task_id,))
        row = cur.fetchone()
        assert row is not None
        assert row["original_goal"] == "Persist Goal"


def test_migration_transaction_rollback_on_failure(tmp_path: Path):
    db_file = tmp_path / "broken_migration.db"
    db = Database(db_file)
    initial_version = db.get_schema_version()

    # Define a failing migration function that raises an exception mid-transaction
    def failing_migration(conn: sqlite3.Connection) -> None:
        conn.execute("CREATE TABLE partial_table (id INTEGER PRIMARY KEY);")
        raise RuntimeError("Disk full or syntax error during migration")

    with pytest.raises(MigrationError, match="Disk full or syntax error"):
        db.execute_transactional_migration(failing_migration, initial_version + 1)

    # Version must NOT have incremented
    assert db.get_schema_version() == initial_version

    # Partial table must have rolled back
    with db.get_connection() as conn:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='partial_table'"
        )
        assert cur.fetchone() is None
