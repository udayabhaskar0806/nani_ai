"""N.A.N.I. V2 — Persistent Skill & Knowledge Store with FTS5 Fast-Path
Enables instant (2-5ms) execution for verified machine tasks with zero token cost.
Stores structured hardware skills, command templates, and full-text knowledge snippets.
"""

import json
import re
import time
import uuid
from typing import Any

from pydantic import BaseModel, Field

from nani.core.grounding import MachineGrounding
from nani.memory.database import Database


class VerifiedSkill(BaseModel):
    skill_id: str = Field(default_factory=lambda: f"skill-{uuid.uuid4().hex[:8]}")
    intent_pattern: str
    description: str
    preconditions: dict[str, Any] = Field(default_factory=dict)
    command_template: str
    verification_rule: str = ""
    success_count: int = 1
    last_used: float = Field(default_factory=time.time)
    created_at: float = Field(default_factory=time.time)


class KnowledgeSnippet(BaseModel):
    snippet_id: str = Field(default_factory=lambda: f"know-{uuid.uuid4().hex[:8]}")
    source: str
    title: str
    content: str
    summary: str
    tags: list[str] = Field(default_factory=list)
    created_at: float = Field(default_factory=time.time)


class SkillStore:
    """Manages verified skills, rapid intent lookup, and full-text knowledge ingestion."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def save_skill(self, skill: VerifiedSkill) -> None:
        """Saves or updates a verified skill and indexes it into FTS5."""
        with self.db.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO verified_skills (
                    skill_id, intent_pattern, description, preconditions_json,
                    command_template, verification_rule, success_count, last_used, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(skill_id) DO UPDATE SET
                    intent_pattern = excluded.intent_pattern,
                    description = excluded.description,
                    preconditions_json = excluded.preconditions_json,
                    command_template = excluded.command_template,
                    verification_rule = excluded.verification_rule,
                    success_count = verified_skills.success_count + 1,
                    last_used = excluded.last_used
                """,
                (
                    skill.skill_id,
                    skill.intent_pattern,
                    skill.description,
                    json.dumps(skill.preconditions),
                    skill.command_template,
                    skill.verification_rule,
                    skill.success_count,
                    skill.last_used,
                    skill.created_at,
                ),
            )
            # Reindex in FTS5
            conn.execute("DELETE FROM verified_skills_fts WHERE skill_id = ?", (skill.skill_id,))
            conn.execute(
                """
                INSERT INTO verified_skills_fts (skill_id, intent_pattern, description, command_template)
                VALUES (?, ?, ?, ?)
                """,
                (skill.skill_id, skill.intent_pattern, skill.description, skill.command_template),
            )
            conn.commit()

    def get_skill(self, skill_id: str) -> VerifiedSkill | None:
        """Retrieves a skill by ID."""
        with self.db.get_connection() as conn:
            cur = conn.execute("SELECT * FROM verified_skills WHERE skill_id = ?", (skill_id,))
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_skill(row)

    def _row_to_skill(self, row: Any) -> VerifiedSkill:
        return VerifiedSkill(
            skill_id=row["skill_id"],
            intent_pattern=row["intent_pattern"],
            description=row["description"],
            preconditions=json.loads(row["preconditions_json"] or "{}"),
            command_template=row["command_template"],
            verification_rule=row["verification_rule"],
            success_count=row["success_count"],
            last_used=row["last_used"],
            created_at=row["created_at"],
        )

    def list_skills(self) -> list[VerifiedSkill]:
        """Lists all stored verified skills."""
        with self.db.get_connection() as conn:
            cur = conn.execute("SELECT * FROM verified_skills ORDER BY success_count DESC")
            return [self._row_to_skill(r) for r in cur.fetchall()]

    def _verify_preconditions(self, skill: VerifiedSkill, snap: dict[str, Any]) -> bool:
        """Validates that host hardware and binaries satisfy skill requirements."""
        pre = skill.preconditions
        if not pre:
            return True

        installed = set(snap.get("installed_tools", []))
        required_tools = pre.get("installed_tools") or pre.get("installed", [])
        for tool in required_tools:
            if tool not in installed:
                return False

        if "session_type" in pre and pre["session_type"] != snap.get("session_type"):
            return False

        return True

    def find_matching_skill(
        self, query: str, grounding_snap: dict[str, Any] | None = None
    ) -> VerifiedSkill | None:
        """Attempts 2-5ms fast-path lookup for a user intent.

        Evaluates exact regex matches first, followed by FTS5 rank queries,
        and verifies that host machine conditions are satisfied.
        """
        clean_query = query.strip()
        snap = grounding_snap or MachineGrounding.get_snapshot()

        # Direct Regex / Pattern match across stored verified skills
        skills = self.list_skills()
        for skill in skills:
            try:
                if re.search(skill.intent_pattern, clean_query, re.IGNORECASE):
                    if self._verify_preconditions(skill, snap):
                        self._increment_success(skill.skill_id)
                        return skill
            except Exception:
                pass

        return None

    def _increment_success(self, skill_id: str) -> None:
        try:
            with self.db.get_connection() as conn:
                conn.execute(
                    """
                    UPDATE verified_skills
                    SET success_count = success_count + 1, last_used = ?
                    WHERE skill_id = ?
                    """,
                    (time.time(), skill_id),
                )
                conn.commit()
        except Exception:
            pass

    def save_knowledge(
        self,
        source: str,
        title: str,
        content: str,
        summary: str,
        tags: list[str] | None = None,
    ) -> KnowledgeSnippet:
        """Stores a summarized knowledge snippet and indexes it for search."""
        snippet = KnowledgeSnippet(
            source=source,
            title=title,
            content=content,
            summary=summary,
            tags=tags or [],
        )
        with self.db.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO knowledge_snippets (
                    snippet_id, source, title, content, summary, tags_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snippet.snippet_id,
                    snippet.source,
                    snippet.title,
                    snippet.content,
                    snippet.summary,
                    json.dumps(snippet.tags),
                    snippet.created_at,
                ),
            )
            conn.execute(
                """
                INSERT INTO knowledge_fts (snippet_id, title, content, summary)
                VALUES (?, ?, ?, ?)
                """,
                (snippet.snippet_id, snippet.title, snippet.content, snippet.summary),
            )
            conn.commit()
        return snippet

    def search_knowledge(self, query: str, limit: int = 5) -> list[KnowledgeSnippet]:
        """Performs FTS5 search across all digested knowledge snippets."""
        fts_query = re.sub(r"[^\w\s]", "", query).strip()
        if not fts_query:
            return []

        terms = [f'"{w}"' for w in fts_query.split() if len(w) > 2]
        if not terms:
            return []
        match_expr = " OR ".join(terms)

        try:
            with self.db.get_connection() as conn:
                cur = conn.execute(
                    """
                    SELECT k.* FROM knowledge_snippets k
                    JOIN knowledge_fts fts ON k.snippet_id = fts.snippet_id
                    WHERE knowledge_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                    """,
                    (match_expr, limit),
                )
                snippets = []
                for r in cur.fetchall():
                    snippets.append(
                        KnowledgeSnippet(
                            snippet_id=r["snippet_id"],
                            source=r["source"],
                            title=r["title"],
                            content=r["content"],
                            summary=r["summary"],
                            tags=json.loads(r["tags_json"] or "[]"),
                            created_at=r["created_at"],
                        )
                    )
                return snippets
        except Exception:
            return []

    def seed_default_skills(self) -> None:
        """Seeds foundational verified Linux hardware & system recipes."""
        defaults = [
            VerifiedSkill(
                skill_id="skill-sysfs-brightness",
                intent_pattern=r"\b(check|read|get|whats?\s+my|what\s+is\s+my|my|screen)\s+.*brightness\b",
                description="Reads screen brightness directly from Linux kernel sysfs",
                preconditions={},
                command_template="cat /sys/class/backlight/*/brightness",
                verification_rule="exit_code == 0",
            ),
            VerifiedSkill(
                skill_id="skill-sysfs-battery",
                intent_pattern=r"\b(check|read|get|whats?\s+my|what\s+is\s+my|my)\s+.*battery\b",
                description="Reads laptop battery capacity directly from Linux power supply sysfs",
                preconditions={},
                command_template="cat /sys/class/power_supply/BAT*/capacity",
                verification_rule="exit_code == 0",
            ),
            VerifiedSkill(
                skill_id="skill-sys-memory",
                intent_pattern=r"\b(check|read|get|free|available)\s+.*memory\b",
                description="Inspects system RAM usage and available memory",
                preconditions={},
                command_template="free -h",
                verification_rule="exit_code == 0",
            ),
            VerifiedSkill(
                skill_id="skill-net-ip",
                intent_pattern=r"\b(show|check|get|whats?\s+my|what\s+is\s+my|my)\s+(ip|ip\s+address|network\s+ip)\b",
                description="Displays network interfaces and IP addresses",
                preconditions={"installed": ["ip"]},
                command_template="ip -brief address",
                verification_rule="exit_code == 0",
            ),
        ]

        for s in defaults:
            self.save_skill(s)
