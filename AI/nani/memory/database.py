"""N.A.N.I. V2 — Persistent Database Schema & Transactional Migrations
Provides SQLite storage with WAL mode, foreign keys, query indexes, and transactional schema migrations.
"""

import sqlite3
import time
from collections.abc import Callable
from pathlib import Path

CURRENT_SCHEMA_VERSION = 1

MIGRATION_V1_SQL = """
PRAGMA foreign_keys = ON;

-- Schema version tracking table
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at REAL NOT NULL
);

-- Persistent Tasks
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    original_goal TEXT NOT NULL,
    interpreted_goal TEXT,
    workspace_path TEXT NOT NULL,
    status TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    current_step_index INTEGER DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    metadata_json TEXT DEFAULT '{}'
);

-- Plan Steps
CREATE TABLE IF NOT EXISTS plan_steps (
    step_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    step_order INTEGER NOT NULL,
    description TEXT NOT NULL,
    capability_required TEXT NOT NULL, -- WorkerCapability (CODING, BROWSER, COMPUTER, SYSTEM, RESEARCH)
    status TEXT NOT NULL,              -- StepStatus (PENDING, IN_PROGRESS, COMPLETED, FAILED, SKIPPED)
    risk_level TEXT NOT NULL,          -- RiskLevel (LOW, MEDIUM, HIGH)
    error TEXT,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
);

-- Action Journal (Every atomic action executed)
CREATE TABLE IF NOT EXISTS actions (
    action_id TEXT PRIMARY KEY,
    task_id TEXT,
    step_id TEXT,
    worker TEXT NOT NULL,
    tool TEXT NOT NULL,
    parameters_json TEXT NOT NULL,
    timestamp REAL NOT NULL,           -- UTC epoch seconds
    duration_ms INTEGER,
    status TEXT NOT NULL,              -- ActionStatus (PENDING, RUNNING, SUCCESS, FAILED, BLOCKED, CANCELLED)
    FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE,
    FOREIGN KEY(step_id) REFERENCES plan_steps(step_id) ON DELETE CASCADE
);

-- Empirical Observations (Evidence gathered after action)
CREATE TABLE IF NOT EXISTS observations (
    observation_id TEXT PRIMARY KEY,
    action_id TEXT,
    step_id TEXT,
    timestamp REAL NOT NULL,           -- UTC epoch seconds
    source TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata_json TEXT DEFAULT '{}',
    FOREIGN KEY(action_id) REFERENCES actions(action_id) ON DELETE CASCADE
);

-- Security Approvals Gate
CREATE TABLE IF NOT EXISTS approvals (
    approval_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    step_id TEXT,
    action_description TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    status TEXT NOT NULL,              -- "PENDING", "APPROVED", "REJECTED"
    requested_at REAL NOT NULL,
    resolved_at REAL,
    FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
);

-- Project Knowledge (Build flags, repo structure, test commands)
CREATE TABLE IF NOT EXISTS projects (
    project_path TEXT PRIMARY KEY,
    project_name TEXT NOT NULL,
    build_system TEXT,
    test_command TEXT,
    compiler_flags TEXT,
    notes TEXT,
    last_inspected REAL NOT NULL
);

-- Episodic Experience (Past problem resolutions)
CREATE TABLE IF NOT EXISTS episodic_memory (
    episode_id TEXT PRIMARY KEY,
    task_id TEXT,
    error_pattern TEXT NOT NULL,
    solution_summary TEXT NOT NULL,
    files_affected_json TEXT DEFAULT '[]',
    timestamp REAL NOT NULL
);

-- Verified Skills & Playbooks
CREATE TABLE IF NOT EXISTS skills (
    skill_name TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    steps_template_json TEXT NOT NULL,
    created_at REAL NOT NULL
);

-- Query Optimization Indexes
CREATE INDEX IF NOT EXISTS idx_plan_steps_task_id ON plan_steps(task_id);
CREATE INDEX IF NOT EXISTS idx_actions_task_id ON actions(task_id);
CREATE INDEX IF NOT EXISTS idx_actions_step_id ON actions(step_id);
CREATE INDEX IF NOT EXISTS idx_observations_action_id ON observations(action_id);
CREATE INDEX IF NOT EXISTS idx_observations_step_id ON observations(step_id);
CREATE INDEX IF NOT EXISTS idx_approvals_task_id ON approvals(task_id);
CREATE INDEX IF NOT EXISTS idx_episodic_memory_task_id ON episodic_memory(task_id);
"""


class MigrationError(Exception):
    """Raised when a transactional database migration fails."""

    pass


class Database:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or Path("data/nani_v2.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.run_migrations()

    def get_connection(self) -> sqlite3.Connection:
        """Creates a connection with WAL mode and foreign keys enabled."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        return conn

    def get_schema_version(self) -> int:
        """Returns the current applied schema version."""
        try:
            with self.get_connection() as conn:
                cur = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
                )
                if not cur.fetchone():
                    return 0
                cur = conn.execute("SELECT MAX(version) FROM schema_version")
                row = cur.fetchone()
                return int(row[0]) if row and row[0] is not None else 0
        except Exception:
            return 0

    def run_migrations(self) -> None:
        """Executes ordered transactional migrations up to CURRENT_SCHEMA_VERSION."""
        migrations: dict[int, Callable[[sqlite3.Connection], None]] = {
            1: self._apply_migration_v1,
        }

        current_ver = self.get_schema_version()
        if current_ver >= CURRENT_SCHEMA_VERSION:
            return

        for target_ver in range(current_ver + 1, CURRENT_SCHEMA_VERSION + 1):
            migration_fn = migrations.get(target_ver)
            if not migration_fn:
                raise MigrationError(f"Missing migration script for schema version {target_ver}")
            self.execute_transactional_migration(migration_fn, target_ver)

    def execute_transactional_migration(
        self, migration_fn: Callable[[sqlite3.Connection], None], target_version: int
    ) -> None:
        """Executes a single migration function atomically within BEGIN TRANSACTION / ROLLBACK."""
        conn = sqlite3.connect(str(self.db_path), isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")

        try:
            conn.execute("BEGIN TRANSACTION;")
            migration_fn(conn)
            conn.execute(
                "INSERT INTO schema_version (version, applied_at) VALUES (?, ?);",
                (target_version, time.time()),
            )
            conn.execute("COMMIT;")
        except Exception as e:
            conn.execute("ROLLBACK;")
            raise MigrationError(
                f"Database migration to version {target_version} failed: {e}"
            ) from e
        finally:
            conn.close()

    def _apply_migration_v1(self, conn: sqlite3.Connection) -> None:
        """Applies schema v1 statements iteratively within the transaction."""
        for raw_stmt in MIGRATION_V1_SQL.split(";"):
            stmt = raw_stmt.strip()
            if stmt:
                conn.execute(stmt)
