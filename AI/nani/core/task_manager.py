"""N.A.N.I. V2 — Task Lifecycle Manager & Persistence Engine
The authoritative component controlling Task lifecycle transitions and SQLite persistence.
Rejects illegal transitions and guarantees crash-resilience across process restarts.
"""

import json
import time
from pathlib import Path
from typing import Any

from nani.core.logger import sanitize_data_structure
from nani.core.task import (
    ALLOWED_TASK_TRANSITIONS,
    Action,
    ActionStatus,
    InvalidTaskTransition,
    Observation,
    PlanStep,
    RiskLevel,
    StepStatus,
    Task,
    TaskStatus,
    WorkerCapability,
)
from nani.memory.database import ConcurrencyError, Database
from nani.memory.journal import ActionJournal


class TaskManager:
    """Sole authoritative controller of task state transitions and persistence."""

    def __init__(self, db: Database | None = None, journal: ActionJournal | None = None) -> None:
        self.db = db or Database()
        self.journal = journal or ActionJournal(self.db)

    def create_task(
        self,
        goal: str,
        workspace_path: str | None = None,
        risk_level: RiskLevel = RiskLevel.LOW,
        metadata: dict[str, Any] | None = None,
    ) -> Task:
        """Instantiates a new Task in CREATED state and persists it immediately."""
        task = Task(
            original_goal=goal,
            workspace_path=str(Path(workspace_path).resolve())
            if workspace_path
            else str(Path.cwd()),
            status=TaskStatus.CREATED,
            risk_level=risk_level,
            metadata=metadata or {},
        )
        self.persist_task(task)
        self.journal.record_transition(
            task_id=task.task_id,
            from_status=TaskStatus.CREATED,
            to_status=TaskStatus.CREATED,
            reason="Task created",
        )
        return task

    def get_task(self, task_id: str) -> Task | None:
        """Retrieves and fully reconstructs a Task and its plan steps from the database."""
        with self.db.get_connection() as conn:
            cur = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,))
            t_row = cur.fetchone()
            if not t_row:
                return None

            cur_steps = conn.execute(
                "SELECT * FROM plan_steps WHERE task_id = ? ORDER BY step_order ASC", (task_id,)
            )
            plan_steps: list[PlanStep] = []
            for s_row in cur_steps.fetchall():
                step_id = s_row["step_id"]

                # Fetch actions for step
                cur_actions = conn.execute(
                    "SELECT * FROM actions WHERE step_id = ? ORDER BY timestamp ASC", (step_id,)
                )
                actions: list[Action] = []
                for a_row in cur_actions.fetchall():
                    actions.append(
                        Action(
                            action_id=a_row["action_id"],
                            step_id=a_row["step_id"],
                            worker=a_row["worker"],
                            tool=a_row["tool"],
                            parameters=json.loads(a_row["parameters_json"] or "{}"),
                            timestamp=a_row["timestamp"],
                            duration_ms=a_row["duration_ms"],
                            status=ActionStatus(a_row["status"]),
                            result=json.loads(a_row["result_json"] or "{}"),
                            error=a_row["error"],
                        )
                    )

                # Fetch observations for step
                cur_obs = conn.execute(
                    "SELECT * FROM observations WHERE step_id = ? ORDER BY timestamp ASC",
                    (step_id,),
                )
                observations: list[Observation] = []
                for o_row in cur_obs.fetchall():
                    observations.append(
                        Observation(
                            observation_id=o_row["observation_id"],
                            action_id=o_row["action_id"],
                            step_id=o_row["step_id"],
                            timestamp=o_row["timestamp"],
                            source=o_row["source"],
                            content=o_row["content"],
                            metadata=json.loads(o_row["metadata_json"] or "{}"),
                        )
                    )

                plan_steps.append(
                    PlanStep(
                        step_id=step_id,
                        order=s_row["step_order"],
                        description=s_row["description"],
                        capability_required=WorkerCapability(s_row["capability_required"]),
                        status=StepStatus(s_row["status"]),
                        risk_level=RiskLevel(s_row["risk_level"]),
                        actions=actions,
                        observations=observations,
                        verification=json.loads(s_row["verification_json"] or "{}"),
                        error=s_row["error"],
                        retry_count=s_row["retry_count"],
                        max_retries=s_row["max_retries"],
                    )
                )

            version = (
                t_row["version"]
                if "version" in t_row.keys() and t_row["version"] is not None
                else 1
            )
            return Task(
                task_id=t_row["task_id"],
                original_goal=t_row["original_goal"],
                interpreted_goal=t_row["interpreted_goal"],
                workspace_path=t_row["workspace_path"],
                status=TaskStatus(t_row["status"]),
                risk_level=RiskLevel(t_row["risk_level"]),
                plan=plan_steps,
                current_step_index=t_row["current_step_index"],
                version=version,
                created_at=t_row["created_at"],
                updated_at=t_row["updated_at"],
                metadata=json.loads(t_row["metadata_json"] or "{}"),
            )

    def restore_task(self, task_id: str) -> Task | None:
        """Alias for get_task; restores task state from persistent SQLite database."""
        return self.get_task(task_id)

    def list_tasks(self, status: TaskStatus | None = None) -> list[Task]:
        """Lists tasks, optionally filtered by status."""
        with self.db.get_connection() as conn:
            if status:
                cur = conn.execute(
                    "SELECT task_id FROM tasks WHERE status = ? ORDER BY created_at DESC",
                    (status.value,),
                )
            else:
                cur = conn.execute("SELECT task_id FROM tasks ORDER BY created_at DESC")
            task_ids = [r["task_id"] for r in cur.fetchall()]

        tasks: list[Task] = []
        for tid in task_ids:
            task = self.get_task(tid)
            if task:
                tasks.append(task)
        return tasks

    def transition_task(
        self,
        task_id: str,
        to_status: TaskStatus,
        reason: str | None = None,
        expected_version: int | None = None,
    ) -> Task:
        """Validates and applies a lifecycle state transition atomically with history and CAS verification."""
        with self.db.get_connection() as conn:
            cur = conn.execute("SELECT status, version FROM tasks WHERE task_id = ?", (task_id,))
            row = cur.fetchone()
            if not row:
                raise KeyError(f"Task '{task_id}' not found.")

            current_status = TaskStatus(row["status"])
            current_ver = (
                row["version"] if "version" in row.keys() and row["version"] is not None else 1
            )

            if expected_version is not None and expected_version != current_ver:
                raise ConcurrencyError(
                    f"CAS conflict: Task '{task_id}' was concurrently modified (expected version {expected_version}, actual version {current_ver})."
                )

            # Terminal state protection
            if current_status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                raise InvalidTaskTransition(
                    f"Illegal task transition: cannot transition from {current_status.value} to {to_status.value}."
                )

            allowed = ALLOWED_TASK_TRANSITIONS.get(current_status, set())
            if to_status not in allowed:
                raise InvalidTaskTransition(
                    f"Illegal task transition: cannot transition from {current_status.value} to {to_status.value}."
                )

            now = time.time()
            # Update task status and increment version atomically with CAS verification
            cur_upd = conn.execute(
                """UPDATE tasks
                   SET status = ?, version = version + 1, updated_at = ?
                   WHERE task_id = ? AND version = ?""",
                (to_status.value, now, task_id, current_ver),
            )
            if cur_upd.rowcount == 0:
                raise ConcurrencyError(
                    f"CAS conflict: Failed to update task '{task_id}' from version {current_ver} due to concurrent modification."
                )

            # Record transition in the SAME transaction
            import uuid

            trans_id = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO task_transitions (transition_id, task_id, from_status, to_status, reason, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (trans_id, task_id, current_status.value, to_status.value, reason, now),
            )
            conn.commit()

        task = self.get_task(task_id)
        assert task is not None
        return task

    def start_task(self, task_id: str) -> Task:
        """Transitions a newly created task to PLANNING."""
        return self.transition_task(task_id, TaskStatus.PLANNING, reason="Starting task planning")

    def pause_task(self, task_id: str) -> Task:
        """Pauses a running task."""
        return self.transition_task(
            task_id, TaskStatus.PAUSED, reason="Task paused by creator/operator"
        )

    def resume_task(self, task_id: str) -> Task:
        """Resumes a paused task back to RUNNING. Strictly rejects resuming WAITING tasks without approval."""
        task = self.get_task(task_id)
        if not task:
            raise KeyError(f"Task '{task_id}' not found.")
        if task.status != TaskStatus.PAUSED:
            raise InvalidTaskTransition(
                f"Cannot resume task in {task.status.value} state. resume_task is only permitted for PAUSED tasks."
            )
        return self.transition_task(task_id, TaskStatus.RUNNING, reason="Task resumed from PAUSED")

    def complete_task(self, task_id: str) -> Task:
        """Marks a verified task as COMPLETED."""
        return self.transition_task(
            task_id, TaskStatus.COMPLETED, reason="All plan steps executed and verified"
        )

    def fail_task(self, task_id: str, reason: str | None = None) -> Task:
        """Transitions a task to FAILED."""
        task = self.get_task(task_id)
        if task:
            task.metadata["error"] = reason or "Task execution failed"
            self.persist_task(task)
        return self.transition_task(
            task_id, TaskStatus.FAILED, reason=reason or "Task execution failed"
        )

    def cancel_task(self, task_id: str, reason: str | None = None) -> Task:
        """Cancels an active task."""
        return self.transition_task(
            task_id, TaskStatus.CANCELLED, reason=reason or "Task cancelled by creator/operator"
        )

    def update_plan(self, task_id: str, plan: list[PlanStep]) -> Task:
        """Replaces the task plan atomically, removing any obsolete steps."""
        task = self.get_task(task_id)
        if not task:
            raise KeyError(f"Task '{task_id}' not found.")

        # In a single transaction, delete old steps and persist the new plan
        with self.db.get_connection() as conn:
            conn.execute("DELETE FROM plan_steps WHERE task_id = ?", (task_id,))
            conn.commit()

        task.plan = plan
        task.mark_updated()
        self.persist_task(task)
        reloaded = self.get_task(task_id)
        assert reloaded is not None
        return reloaded

    def set_current_step_index(self, task_id: str, index: int) -> Task:
        """Updates the current execution step pointer and persists it."""
        task = self.get_task(task_id)
        if not task:
            raise KeyError(f"Task '{task_id}' not found.")
        task.current_step_index = index
        task.mark_updated()
        self.persist_task(task)
        return task

    def persist_task(self, task: Task, expected_version: int | None = None) -> None:
        """Persists the Task state atomically to SQLite with secret redaction, terminal protection, and CAS."""
        task.mark_updated()
        safe_metadata = sanitize_data_structure(task.metadata)
        meta_json = json.dumps(safe_metadata)

        with self.db.get_connection() as conn:
            # Check terminal state protection: do NOT overwrite CANCELLED/FAILED/COMPLETED task with active state
            cur = conn.execute(
                "SELECT status, version FROM tasks WHERE task_id = ?", (task.task_id,)
            )
            row = cur.fetchone()
            if row:
                db_status = TaskStatus(row["status"])
                if db_status in (
                    TaskStatus.CANCELLED,
                    TaskStatus.FAILED,
                    TaskStatus.COMPLETED,
                ) and task.status not in (
                    TaskStatus.CANCELLED,
                    TaskStatus.FAILED,
                    TaskStatus.COMPLETED,
                ):
                    # Stale update protection: prevent overwriting terminal status
                    return

                current_ver = (
                    row["version"] if "version" in row.keys() and row["version"] is not None else 1
                )
                if expected_version is not None and expected_version != current_ver:
                    raise ConcurrencyError(
                        f"CAS conflict in persist_task: Task '{task.task_id}' was concurrently modified (expected version {expected_version}, actual {current_ver})."
                    )

                cur_upd = conn.execute(
                    """UPDATE tasks SET
                           original_goal = ?,
                           interpreted_goal = ?,
                           workspace_path = ?,
                           status = ?,
                           risk_level = ?,
                           current_step_index = ?,
                           version = version + 1,
                           updated_at = ?,
                           metadata_json = ?
                       WHERE task_id = ? AND version = ?""",
                    (
                        task.original_goal,
                        task.interpreted_goal,
                        task.workspace_path,
                        task.status.value,
                        task.risk_level.value,
                        task.current_step_index,
                        task.updated_at,
                        meta_json,
                        task.task_id,
                        current_ver,
                    ),
                )
                if cur_upd.rowcount == 0:
                    raise ConcurrencyError(
                        f"CAS conflict: Failed to update task '{task.task_id}' from version {current_ver} due to concurrent modification."
                    )
                task.version = current_ver + 1
            else:
                conn.execute(
                    """INSERT INTO tasks (
                           task_id, original_goal, interpreted_goal, workspace_path,
                           status, risk_level, current_step_index, version, created_at, updated_at, metadata_json
                       )
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        task.task_id,
                        task.original_goal,
                        task.interpreted_goal,
                        task.workspace_path,
                        task.status.value,
                        task.risk_level.value,
                        task.current_step_index,
                        task.version,
                        task.created_at,
                        task.updated_at,
                        meta_json,
                    ),
                )

            for step in task.plan:
                safe_ver = sanitize_data_structure(step.verification)
                ver_json = json.dumps(safe_ver)
                conn.execute(
                    """INSERT INTO plan_steps (
                           step_id, task_id, step_order, description, capability_required,
                           status, risk_level, verification_json, error, retry_count, max_retries
                       )
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(step_id) DO UPDATE SET
                           step_order = excluded.step_order,
                           description = excluded.description,
                           capability_required = excluded.capability_required,
                           status = excluded.status,
                           risk_level = excluded.risk_level,
                           verification_json = excluded.verification_json,
                           error = excluded.error,
                           retry_count = excluded.retry_count,
                           max_retries = excluded.max_retries""",
                    (
                        step.step_id,
                        task.task_id,
                        step.order,
                        step.description,
                        step.capability_required.value,
                        step.status.value,
                        step.risk_level.value,
                        ver_json,
                        step.error,
                        step.retry_count,
                        step.max_retries,
                    ),
                )

                for act in step.actions:
                    safe_params = sanitize_data_structure(act.parameters)
                    safe_res = sanitize_data_structure(act.result)
                    params_json = json.dumps(safe_params)
                    res_json = json.dumps(safe_res)
                    conn.execute(
                        """INSERT INTO actions (
                               action_id, task_id, step_id, worker, tool,
                               parameters_json, timestamp, duration_ms, status, result_json, error
                           )
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                           ON CONFLICT(action_id) DO UPDATE SET
                               parameters_json = excluded.parameters_json,
                               duration_ms = excluded.duration_ms,
                               status = excluded.status,
                               result_json = excluded.result_json,
                               error = excluded.error""",
                        (
                            act.action_id,
                            task.task_id,
                            step.step_id,
                            act.worker,
                            act.tool,
                            params_json,
                            act.timestamp,
                            act.duration_ms,
                            act.status.value,
                            res_json,
                            act.error,
                        ),
                    )

                for obs in step.observations:
                    safe_obs_meta = sanitize_data_structure(obs.metadata)
                    obs_meta_json = json.dumps(safe_obs_meta)
                    conn.execute(
                        """INSERT INTO observations (
                               observation_id, action_id, step_id, timestamp, source, content, metadata_json
                           )
                           VALUES (?, ?, ?, ?, ?, ?, ?)
                           ON CONFLICT(observation_id) DO UPDATE SET
                               content = excluded.content,
                               metadata_json = excluded.metadata_json""",
                        (
                            obs.observation_id,
                            obs.action_id,
                            step.step_id,
                            obs.timestamp,
                            obs.source,
                            obs.content,
                            obs_meta_json,
                        ),
                    )

            conn.commit()
