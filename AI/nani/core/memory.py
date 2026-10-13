"""N.A.N.I. Memory Store (SQLite-based)
Persists user profile, thoughts, reminders, notes, and research history.
"""

import sqlite3
from datetime import datetime
from typing import List, Dict, Optional, Any
from nani.config import Config

class MemoryStore:
    def __init__(self, db_path=Config.DB_PATH):
        self.db_path = str(db_path)
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            
            # User profile (skills, preferences, goals)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS profile (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT
            )
            """)

            # Reminders & Tasks
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task TEXT NOT NULL,
                trigger_time TEXT NOT NULL,
                created_at TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                channel TEXT DEFAULT 'terminal'
            )
            """)

            # Knowledge Notes
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """)

            # Chat History
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
            """)

            # GitHub Radar Saved Repos
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS repo_radar (
                repo_name TEXT PRIMARY KEY,
                url TEXT,
                description TEXT,
                stars INTEGER,
                summary TEXT,
                discovered_at TEXT
            )
            """)

            conn.commit()

        # Seed default profile if empty
        self._seed_default_profile()

    def _seed_default_profile(self):
        defaults = {
            "creator_expertise": "C, C++, Linux internals, Networking, OpenGL, CPU architecture",
            "thinking_style": "First-principles systems reasoning, deep inquisitive analysis (Why? Why?)",
            "goals": "Build personal AI co-pilot (N.A.N.I.), research frontier GitHub AI repos, automate reminders and workflow",
            "hardware": "Intel Core i5-1155G7 (AVX-512), 8GB RAM, Linux"
        }
        for k, v in defaults.items():
            self.set_profile_key(k, v, overwrite_if_empty_only=True)

    def set_profile_key(self, key: str, value: str, overwrite_if_empty_only: bool = False):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            if overwrite_if_empty_only:
                cursor.execute("SELECT value FROM profile WHERE key = ?", (key,))
                if cursor.fetchone():
                    return
            cursor.execute(
                "INSERT OR REPLACE INTO profile (key, value, updated_at) VALUES (?, ?, ?)",
                (key, value, datetime.now().isoformat())
            )
            conn.commit()

    def get_profile_summary(self) -> str:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM profile")
            rows = cursor.fetchall()
            return "\n".join([f"- {row['key']}: {row['value']}" for row in rows])

    # Reminders
    def add_reminder(self, task: str, trigger_time: str, channel: str = "terminal") -> int:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO reminders (task, trigger_time, created_at, status, channel) VALUES (?, ?, ?, ?, ?)",
                (task, trigger_time, datetime.now().isoformat(), "pending", channel)
            )
            conn.commit()
            return cursor.lastrowid

    def get_pending_reminders(self) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM reminders WHERE status = 'pending' ORDER BY trigger_time ASC")
            return [dict(row) for row in cursor.fetchall()]

    def mark_reminder_done(self, reminder_id: int):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE reminders SET status = 'completed' WHERE id = ?", (reminder_id,))
            conn.commit()

    # Notes
    def add_note(self, topic: str, content: str) -> int:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO notes (topic, content, created_at) VALUES (?, ?, ?)",
                (topic, content, datetime.now().isoformat())
            )
            conn.commit()
            return cursor.lastrowid

    def get_recent_notes(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM notes ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]

    # Conversations
    def log_message(self, role: str, content: str):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO conversations (role, content, timestamp) VALUES (?, ?, ?)",
                (role, content, datetime.now().isoformat())
            )
            conn.commit()

    def get_recent_history(self, limit: int = 6) -> List[Dict[str, str]]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT role, content FROM conversations ORDER BY id DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            # Return in chronological order
            return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]
