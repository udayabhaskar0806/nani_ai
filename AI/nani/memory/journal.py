"""N.A.N.I. V2 — Structured Action Journal & Episodic Execution Memory
Provides durable, sanitized, and auditable recording of actions, transitions, observations, and approvals in SQLite.
"""

import json
import time
import uuid
from typing import Any

from nani.core.logger import logger as global_logger
from nani.core.logger import redact_sensitive_data, sanitize_data_structure
from nani.core.task import ActionStatus, RiskLevel, TaskStatus
from nani.memory.database import Database


class ActionJournal:
    """Structured append-only episodic execution journal providing sanitized execution history."""

    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()

    def _sanitize_data(self, data: Any) -> Any:
        """Recursively stringifies and redacts sensitive information."""
        return sanitize_data_structure(data)

    def record_action_start(
        self,
        task_id: str,
        step_id: str | None,
        worker: str,
        tool: str,
        parameters: dict[str, Any],
        action_id: str | None = None,
    ) -> str:
        """Records the invocation of an atomic tool action."""
        act_id = action_id or str(uuid.uuid4())
        now = time.time()
        safe_params = self._sanitize_data(parameters)
        params_json = json.dumps(safe_params)

        with self.db.get_connection() as conn:
            valid_step_id: str | None = None
            if step_id:
                cur = conn.execute("SELECT step_id FROM plan_steps WHERE step_id = ?", (step_id,))
                if cur.fetchone():
                    valid_step_id = step_id

            conn.execute(
                """INSERT INTO actions (action_id, task_id, step_id, worker, tool, parameters_json, timestamp, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    act_id,
                    task_id,
                    valid_step_id,
                    worker,
                    tool,
                    params_json,
                    now,
                    ActionStatus.RUNNING.value,
                ),
            )
            entry_id = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO journal_entries (entry_id, task_id, step_id, action_id, entry_type, worker, tool, status, parameters_json, timestamp)
                   VALUES (?, ?, ?, ?, 'ACTION_START', ?, ?, ?, ?, ?)""",
                (
                    entry_id,
                    task_id,
                    step_id,
                    act_id,
                    worker,
                    tool,
                    ActionStatus.RUNNING.value,
                    params_json,
                    now,
                ),
            )
            conn.commit()

        global_logger.log_event(
            event_type="ACTION_START",
            task_id=task_id,
            step_id=step_id,
            worker=worker,
            tool=tool,
            status=ActionStatus.RUNNING.value,
            data={"action_id": act_id, "parameters": safe_params},
        )
        return act_id

    def record_action_result(
        self,
        action_id: str,
        status: ActionStatus,
        duration_ms: int,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        task_id: str | None = None,
        step_id: str | None = None,
        worker: str | None = None,
        tool: str | None = None,
    ) -> None:
        """Records the outcome of an atomic action."""
        now = time.time()
        safe_res = self._sanitize_data(result or {})
        safe_err = redact_sensitive_data(error) if error else None
        res_json = json.dumps(safe_res)

        with self.db.get_connection() as conn:
            if not (task_id and worker and tool):
                cur = conn.execute(
                    "SELECT task_id, step_id, worker, tool FROM actions WHERE action_id = ?",
                    (action_id,),
                )
                row = cur.fetchone()
                if row:
                    task_id = task_id or row["task_id"]
                    step_id = step_id or row["step_id"]
                    worker = worker or row["worker"]
                    tool = tool or row["tool"]

            conn.execute(
                """UPDATE actions
                   SET status = ?, duration_ms = ?, result_json = ?, error = ?
                   WHERE action_id = ?""",
                (status.value, duration_ms, res_json, safe_err, action_id),
            )
            entry_id = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO journal_entries (entry_id, task_id, step_id, action_id, entry_type, worker, tool, status, duration_ms, result_json, error, timestamp)
                   VALUES (?, ?, ?, ?, 'ACTION_RESULT', ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry_id,
                    task_id,
                    step_id,
                    action_id,
                    worker,
                    tool,
                    status.value,
                    duration_ms,
                    res_json,
                    safe_err,
                    now,
                ),
            )
            conn.commit()

        global_logger.log_event(
            event_type="ACTION_RESULT",
            task_id=task_id,
            step_id=step_id,
            worker=worker,
            tool=tool,
            status=status.value,
            duration_ms=duration_ms,
            data={"action_id": action_id, "result": safe_res, "error": safe_err},
        )

    def record_observation(
        self,
        source: str,
        content: str,
        action_id: str | None = None,
        step_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        task_id: str | None = None,
    ) -> str:
        """Records empirical sensory or output evidence gathered during task execution."""
        obs_id = str(uuid.uuid4())
        now = time.time()
        safe_content = redact_sensitive_data(content[:50_000])
        safe_meta = self._sanitize_data(metadata or {})
        meta_json = json.dumps(safe_meta)

        with self.db.get_connection() as conn:
            if not task_id and action_id:
                cur = conn.execute(
                    "SELECT task_id, step_id FROM actions WHERE action_id = ?", (action_id,)
                )
                row = cur.fetchone()
                if row:
                    task_id = row["task_id"]
                    step_id = step_id or row["step_id"]

            valid_action_id: str | None = None
            if action_id:
                cur = conn.execute(
                    "SELECT action_id FROM actions WHERE action_id = ?", (action_id,)
                )
                if cur.fetchone():
                    valid_action_id = action_id

            valid_step_id: str | None = None
            if step_id:
                cur = conn.execute("SELECT step_id FROM plan_steps WHERE step_id = ?", (step_id,))
                if cur.fetchone():
                    valid_step_id = step_id

            conn.execute(
                """INSERT INTO observations (observation_id, task_id, action_id, step_id, timestamp, source, content, metadata_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    obs_id,
                    task_id,
                    valid_action_id,
                    valid_step_id,
                    now,
                    source,
                    safe_content,
                    meta_json,
                ),
            )
            entry_id = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO journal_entries (entry_id, task_id, step_id, action_id, entry_type, status, metadata_json, timestamp)
                   VALUES (?, ?, ?, ?, 'OBSERVATION', 'RECORDED', ?, ?)""",
                (entry_id, task_id, step_id, action_id, meta_json, now),
            )
            conn.commit()

        global_logger.log_event(
            event_type="OBSERVATION",
            task_id=task_id,
            step_id=step_id,
            status="INFO",
            data={
                "observation_id": obs_id,
                "action_id": action_id,
                "source": source,
                "content": safe_content,
                "metadata": safe_meta,
            },
        )
        return obs_id

    def record_transition(
        self,
        task_id: str,
        from_status: TaskStatus,
        to_status: TaskStatus,
        reason: str | None = None,
    ) -> None:
        """Persists task state lifecycle transition into audit history."""
        now = time.time()
        trans_id = str(uuid.uuid4())
        safe_reason = redact_sensitive_data(reason) if reason else None

        with self.db.get_connection() as conn:
            conn.execute(
                """INSERT INTO task_transitions (transition_id, task_id, from_status, to_status, reason, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (trans_id, task_id, from_status.value, to_status.value, safe_reason, now),
            )
            entry_id = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO journal_entries (entry_id, task_id, entry_type, status, error, timestamp)
                   VALUES (?, ?, 'TRANSITION', ?, ?, ?)""",
                (entry_id, task_id, to_status.value, safe_reason, now),
            )
            conn.commit()

        global_logger.log_event(
            event_type="TRANSITION",
            task_id=task_id,
            status=to_status.value,
            data={
                "transition_id": trans_id,
                "from_status": from_status.value,
                "to_status": to_status.value,
                "reason": safe_reason,
            },
        )

    def record_error(
        self,
        task_id: str,
        step_id: str | None,
        error: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Records an execution error or diagnosis context."""
        now = time.time()
        entry_id = str(uuid.uuid4())
        safe_err = redact_sensitive_data(error)
        safe_ctx = self._sanitize_data(context or {})
        ctx_json = json.dumps(safe_ctx)

        with self.db.get_connection() as conn:
            conn.execute(
                """INSERT INTO journal_entries (entry_id, task_id, step_id, entry_type, status, error, metadata_json, timestamp)
                   VALUES (?, ?, ?, 'ERROR', 'FAILED', ?, ?, ?)""",
                (entry_id, task_id, step_id, safe_err, ctx_json, now),
            )
            conn.commit()

        global_logger.log_event(
            event_type="ERROR",
            task_id=task_id,
            step_id=step_id,
            status="ERROR",
            data={"error": safe_err, "context": safe_ctx},
        )

    def record_approval_request(
        self,
        task_id: str,
        step_id: str | None,
        action_description: str,
        risk_level: RiskLevel,
    ) -> str:
        """Logs an escalation gate requiring creator confirmation, deduplicating active pending requests."""
        now = time.time()
        safe_desc = redact_sensitive_data(action_description)

        with self.db.get_connection() as conn:
            # Check for existing pending approval request to deduplicate
            cur = conn.execute(
                "SELECT approval_id FROM approvals WHERE task_id = ? AND action_description = ? AND status = 'PENDING'",
                (task_id, safe_desc),
            )
            existing = cur.fetchone()
            if existing:
                return str(existing["approval_id"])

            approval_id = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO approvals (approval_id, task_id, step_id, action_description, risk_level, status, requested_at)
                   VALUES (?, ?, ?, ?, ?, 'PENDING', ?)""",
                (approval_id, task_id, step_id, safe_desc, risk_level.value, now),
            )
            entry_id = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO journal_entries (entry_id, task_id, step_id, entry_type, status, metadata_json, timestamp)
                   VALUES (?, ?, ?, 'APPROVAL_REQUEST', 'WAITING', ?, ?)""",
                (
                    entry_id,
                    task_id,
                    step_id,
                    json.dumps(
                        {
                            "approval_id": approval_id,
                            "risk_level": risk_level.value,
                            "description": safe_desc,
                        }
                    ),
                    now,
                ),
            )
            conn.commit()

        global_logger.log_event(
            event_type="APPROVAL_REQUEST",
            task_id=task_id,
            step_id=step_id,
            status="WAITING",
            data={
                "approval_id": approval_id,
                "action_description": safe_desc,
                "risk_level": risk_level.value,
            },
        )
        return approval_id

    def reconstruct_task_history(self, task_id: str) -> dict[str, Any]:
        """Reconstructs complete episodic execution memory from SQLite records."""
        with self.db.get_connection() as conn:
            # 1. Task metadata
            cur = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,))
            task_row = cur.fetchone()
            if not task_row:
                raise KeyError(f"Task '{task_id}' not found in database.")

            # 2. Plan steps
            cur = conn.execute(
                "SELECT * FROM plan_steps WHERE task_id = ? ORDER BY step_order ASC",
                (task_id,),
            )
            steps = []
            for r in cur.fetchall():
                steps.append(
                    {
                        "step_id": r["step_id"],
                        "order": r["step_order"],
                        "description": r["description"],
                        "capability_required": r["capability_required"],
                        "status": r["status"],
                        "risk_level": r["risk_level"],
                        "error": r["error"],
                        "retry_count": r["retry_count"],
                        "max_retries": r["max_retries"],
                        "verification": json.loads(r["verification_json"] or "{}"),
                    }
                )

            # 3. State transitions
            cur = conn.execute(
                "SELECT * FROM task_transitions WHERE task_id = ? ORDER BY timestamp ASC",
                (task_id,),
            )
            transitions = [
                {
                    "transition_id": r["transition_id"],
                    "from_status": r["from_status"],
                    "to_status": r["to_status"],
                    "reason": r["reason"],
                    "timestamp": r["timestamp"],
                }
                for r in cur.fetchall()
            ]

            # 4. Actions
            cur = conn.execute(
                "SELECT * FROM actions WHERE task_id = ? ORDER BY timestamp ASC",
                (task_id,),
            )
            actions = []
            tools_called: list[str] = []
            exit_codes: list[int] = []
            durations: list[int] = []

            for r in cur.fetchall():
                tool_name = r["tool"]
                tools_called.append(tool_name)
                duration = r["duration_ms"] or 0
                durations.append(duration)

                res_dict = json.loads(r["result_json"] or "{}")
                if "exit_code" in res_dict and res_dict["exit_code"] is not None:
                    exit_codes.append(int(res_dict["exit_code"]))

                actions.append(
                    {
                        "action_id": r["action_id"],
                        "step_id": r["step_id"],
                        "worker": r["worker"],
                        "tool": tool_name,
                        "parameters": json.loads(r["parameters_json"] or "{}"),
                        "status": r["status"],
                        "duration_ms": duration,
                        "result": res_dict,
                        "error": r["error"],
                        "timestamp": r["timestamp"],
                    }
                )

            # 5. Observations
            cur = conn.execute(
                """SELECT o.* FROM observations o
                   LEFT JOIN actions a ON o.action_id = a.action_id
                   WHERE o.task_id = ? OR a.task_id = ? OR o.step_id IN (SELECT step_id FROM plan_steps WHERE task_id = ?)
                   ORDER BY o.timestamp ASC""",
                (task_id, task_id, task_id),
            )
            observations = []
            for r in cur.fetchall():
                obs_meta = json.loads(r["metadata_json"] or "{}")
                if "exit_code" in obs_meta and obs_meta["exit_code"] is not None:
                    exit_codes.append(int(obs_meta["exit_code"]))
                observations.append(
                    {
                        "observation_id": r["observation_id"],
                        "action_id": r["action_id"],
                        "step_id": r["step_id"],
                        "source": r["source"],
                        "content": r["content"],
                        "metadata": obs_meta,
                        "timestamp": r["timestamp"],
                    }
                )

            # 6. Approvals
            cur = conn.execute(
                "SELECT * FROM approvals WHERE task_id = ? ORDER BY requested_at ASC",
                (task_id,),
            )
            approvals = [
                {
                    "approval_id": r["approval_id"],
                    "step_id": r["step_id"],
                    "action_description": r["action_description"],
                    "risk_level": r["risk_level"],
                    "status": r["status"],
                    "requested_at": r["requested_at"],
                    "resolved_at": r["resolved_at"],
                }
                for r in cur.fetchall()
            ]

            return {
                "task_id": task_row["task_id"],
                "goal": task_row["original_goal"],
                "workspace_path": task_row["workspace_path"],
                "final_status": task_row["status"],
                "risk_level": task_row["risk_level"],
                "current_step_index": task_row["current_step_index"],
                "created_at": task_row["created_at"],
                "updated_at": task_row["updated_at"],
                "plan": steps,
                "state_transitions": transitions,
                "actions": actions,
                "observations": observations,
                "approvals": approvals,
                "tools_called": tools_called,
                "exit_codes": exit_codes,
                "durations": durations,
                "total_duration_ms": sum(durations),
            }
