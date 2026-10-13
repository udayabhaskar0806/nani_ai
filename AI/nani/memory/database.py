"""N.A.N.I. V2 — Persistent Database Schema & Storage
Initializes SQLite database with foreign keys, WAL mode, and schema version tracking.
"""

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1

INIT_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- Schema version tracking
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
    capability_required TEXT NOT NULL,
    status TEXT NOT NULL,
    risk_level TEXT NOT NULL,
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
    timestamp REAL NOT NULL,
    duration_ms INTEGER,
    status TEXT NOT NULL,
    FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE,
    FOREIGN KEY(step_id) REFERENCES plan_steps(step_id) ON DELETE CASCADE
);

-- Empirical Observations (Evidence gathered after action)
CREATE TABLE IF NOT EXISTS observations (
    observation_id TEXT PRIMARY KEY,
    action_id TEXT,
    step_id TEXT,
    timestamp REAL NOT NULL,
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
    status TEXT NOT NULL, -- "PENDING", "APPROVED", "REJECTED"
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
"""


class Database:
    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or Path("data/nani_v2.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        return conn

    def init_schema(self) -> None:
        with self.get_connection() as conn:
            conn.executescript(INIT_SQL)
            # Check version
            cur = conn.execute(
                "SELECT version FROM schema_version WHERE version = ?", (SCHEMA_VERSION,)
            )
            if not cur.fetchone():
                import time

                conn.execute(
                    "INSERT OR REPLACE INTO schema_version (version, applied_at) VALUES (?, ?)",
                    (SCHEMA_VERSION, time.time()),
                )
            conn.commit()

    def get_schema_version(self) -> int:
        with self.get_connection() as conn:
            cur = conn.execute("SELECT MAX(version) FROM schema_version")
            row = cur.fetchone()
            return int(row[0]) if row and row[0] is not None else 0
