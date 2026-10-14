"""N.A.N.I. V2 — Minimal Autonomous Runtime Orchestrator
Coordinates TaskManager, Planner, CapabilityRouter, ToolRegistry, Verifier, and Recovery.
Maintains interruptibility and enforces strict state transitions without direct database or subprocess access.
"""

import json
import uuid
from pathlib import Path
from typing import Any

from nani.core.context import ExecutionContext
from nani.core.planner import Planner
from nani.core.recovery import RecoveryManager
from nani.core.router import CapabilityRouter
from nani.core.task import ActionStatus, PlanStep, StepStatus, Task, TaskStatus
from nani.core.task_manager import TaskManager
from nani.core.verifier import Verifier
from nani.memory.journal import ActionJournal
from nani.tools.registry import ToolRegistry
from nani.tools.result import ToolResult

IDEMPOTENT_TOOLS = frozenset(
    {
        "read_file",
        "list_directory",
        "search_files",
        "file_exists",
        "git",
    }
)


class Orchestrator:
    """Coordinates deterministic autonomous task execution across modular subsystems."""

    def __init__(
        self,
        task_manager: TaskManager,
        tool_registry: ToolRegistry,
        planner: Planner | None = None,
        router: CapabilityRouter | None = None,
        verifier: Verifier | None = None,
        recovery: RecoveryManager | None = None,
        journal: ActionJournal | None = None,
    ) -> None:
        self.task_manager = task_manager
        self.tool_registry = tool_registry
        self.planner = planner or Planner()
        self.router = router or CapabilityRouter()
        self.verifier = verifier or Verifier()
        self.recovery = recovery or RecoveryManager()
        self.journal = journal or task_manager.journal
        self._pause_requested: bool = False

    def request_pause(self) -> None:
        """Flags the orchestrator to pause execution at the next step boundary."""
        self._pause_requested = True

    async def run_task(
        self,
        task_id: str,
        predefined_steps: list[PlanStep] | None = None,
    ) -> Task:
        """Executes the task through its full lifecycle loop.

        Handles CREATED, PLANNING, RUNNING, WAITING, PAUSED, RECOVERY, and VERIFYING safely.
        """
        task = self.task_manager.get_task(task_id)
        if not task:
            raise KeyError(f"Task '{task_id}' not found.")

        # Phase 1: Planning initialization or lifecycle recovery
        if task.status == TaskStatus.CREATED or task.status == TaskStatus.PLANNING:
            if task.status == TaskStatus.CREATED:
                task = self.task_manager.transition_task(
                    task_id, TaskStatus.PLANNING, reason="Generating task execution plan"
                )

            try:
                plan = self.planner.plan(
                    goal=task.original_goal,
                    predefined_steps=predefined_steps,
                    task_metadata=task.metadata,
                )
            except Exception as e:
                return self.task_manager.fail_task(task_id, reason=f"Planning failed: {e}")

            task = self.task_manager.update_plan(task_id, plan)
            task = self.task_manager.transition_task(
                task_id, TaskStatus.RUNNING, reason="Starting plan execution"
            )

        elif task.status == TaskStatus.PAUSED:
            task = self.task_manager.resume_task(task_id)

        elif task.status == TaskStatus.RECOVERY:
            # Lifecycle recovery for RECOVERY state: re-evaluate failure or resume
            if task.current_step_index < len(task.plan):
                step = task.plan[task.current_step_index]
                if step.retry_count < step.max_retries:
                    task = self.task_manager.transition_task(
                        task_id, TaskStatus.RUNNING, reason="Resuming from recovery state"
                    )
                else:
                    return self.task_manager.fail_task(
                        task_id, reason="Recovery exhausted maximum retries on restart."
                    )
            else:
                return self.task_manager.fail_task(
                    task_id, reason="Invalid step index during recovery restart."
                )

        elif task.status == TaskStatus.VERIFYING:
            # Lifecycle recovery for VERIFYING state
            final_ver = self.verifier.verify_task(task, workspace_path=task.workspace_path)
            if final_ver.verified:
                return self.task_manager.complete_task(task_id)
            else:
                return self.task_manager.fail_task(
                    task_id,
                    reason="Final task plan verification failed during restart verification",
                )

        elif task.status in (
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
            TaskStatus.WAITING,
        ):
            return task

        # Phase 2: Step execution loop
        while task.current_step_index < len(task.plan):
            # Check interruptibility between steps
            latest_task = self.task_manager.get_task(task_id)
            if not latest_task:
                break
            task = latest_task

            if self._pause_requested or task.status == TaskStatus.PAUSED:
                if task.status != TaskStatus.PAUSED:
                    task = self.task_manager.pause_task(task_id)
                self._pause_requested = False
                return task

            if task.status in (TaskStatus.CANCELLED, TaskStatus.FAILED, TaskStatus.WAITING):
                return task

            if task.status != TaskStatus.RUNNING:
                break

            step = task.plan[task.current_step_index]

            # Crash/Resume safety: skip already completed steps
            if step.status == StepStatus.COMPLETED:
                task.current_step_index += 1
                task = self.task_manager.set_current_step_index(task_id, task.current_step_index)
                continue

            # Route capability
            decision = self.router.route(step)

            # Determine tool and parameters
            tool_name: str
            worker: str
            params: dict[str, Any]

            if step.actions:
                act = step.actions[0]
                tool_name = act.tool
                worker = act.worker or decision.worker
                params = dict(act.parameters)
            else:
                tool_name = decision.suggested_tool
                worker = decision.worker
                params = {}

            # Construct trusted ExecutionContext (no caller-controlled workspace overrides)
            attempt_id = str(uuid.uuid4())
            context = ExecutionContext(
                task_id=task.task_id,
                step_id=step.step_id,
                attempt_id=attempt_id,
                workspace=Path(task.workspace_path).resolve(),
            )

            # Crash reconciliation check: check if this step was previously in-flight or succeeded
            with self.task_manager.db.get_connection() as conn:
                cur = conn.execute(
                    "SELECT action_id, status, result_json, error FROM actions WHERE step_id = ? ORDER BY timestamp DESC LIMIT 1",
                    (step.step_id,),
                )
                last_act = cur.fetchone()

            if last_act:
                act_status = last_act["status"]

                if act_status == ActionStatus.SUCCESS.value:
                    # Action already succeeded prior to crash! Reconcile result and advance without replaying
                    res_raw = json.loads(last_act["result_json"] or "{}")
                    recovered_res = ToolResult.ok(
                        data=res_raw.get("data"),
                        stdout=res_raw.get("stdout", ""),
                        stderr=res_raw.get("stderr", ""),
                    )
                    ver_check = self.verifier.verify_step(
                        step=step, result=recovered_res, workspace_path=task.workspace_path
                    )
                    if ver_check.verified:
                        step.status = StepStatus.COMPLETED
                        task.current_step_index += 1
                        self.task_manager.persist_task(task)
                        task = self.task_manager.set_current_step_index(
                            task.task_id, task.current_step_index
                        )
                        continue
                    else:
                        return self.task_manager.fail_task(
                            task_id,
                            reason=f"Crash recovery halted: recovered action succeeded but verification failed: {'; '.join(ver_check.failure_reasons)}",
                        )

                elif act_status == ActionStatus.RUNNING.value:
                    # Action crashed mid-flight while RUNNING
                    if tool_name not in IDEMPOTENT_TOOLS:
                        # Non-idempotent tool: require explicit empirical verification criteria
                        has_empirical = bool(
                            step.verification
                            and any(
                                k in step.verification
                                for k in ("path", "type", "checks", "expected_content", "regex")
                            )
                            and step.verification.get("type") != "default_success"
                        )
                        if not has_empirical:
                            return self.task_manager.fail_task(
                                task_id,
                                reason=f"Crash recovery halted: non-idempotent operation '{tool_name}' was interrupted mid-execution with no empirical verification criteria. Refusing to replay uncertain side effect.",
                            )

                        ver_check = self.verifier.verify_step(
                            step=step, result=None, workspace_path=task.workspace_path
                        )
                        if ver_check.verified:
                            step.status = StepStatus.COMPLETED
                            task.current_step_index += 1
                            self.task_manager.persist_task(task)
                            task = self.task_manager.set_current_step_index(
                                task.task_id, task.current_step_index
                            )
                            continue
                        else:
                            return self.task_manager.fail_task(
                                task_id,
                                reason=f"Crash recovery halted: non-idempotent operation '{tool_name}' was interrupted mid-execution and empirical verification failed: {'; '.join(ver_check.failure_reasons)}.",
                            )

            # Mark step in progress
            step.status = StepStatus.IN_PROGRESS
            self.task_manager.persist_task(task)

            # Execute tool through security and journal gate
            result = await self.tool_registry.execute(
                name=tool_name,
                parameters=params,
                task_id=task.task_id,
                step_id=step.step_id,
                worker=worker,
                journal=self.journal,
                context=context,
            )

            # Preserving cancellation / pause in-flight:
            fresh_task = self.task_manager.get_task(task_id)
            if not fresh_task or fresh_task.status in (
                TaskStatus.CANCELLED,
                TaskStatus.PAUSED,
                TaskStatus.FAILED,
            ):
                return fresh_task or task

            # Security gate: High risk requires creator approval -> WAITING
            if result.metadata.get("approval_required"):
                step.status = StepStatus.PENDING
                self.task_manager.persist_task(task)
                task = self.task_manager.transition_task(
                    task.task_id,
                    TaskStatus.WAITING,
                    reason=f"Security gate: approval required for operation '{tool_name}'",
                )
                return task

            # Record observation
            obs_content = result.stdout or result.stderr or str(result.data)
            obs_source = "stdout" if result.stdout else ("stderr" if result.stderr else "tool_data")
            if self.journal:
                self.journal.record_observation(
                    source=obs_source,
                    content=obs_content,
                    action_id=attempt_id,
                    step_id=step.step_id,
                    metadata={"exit_code": result.exit_code, "success": result.success},
                    task_id=task.task_id,
                )

            # Verify step evidence
            verification = self.verifier.verify_step(
                step=step,
                result=result,
                workspace_path=task.workspace_path,
            )

            if verification.verified:
                step.status = StepStatus.COMPLETED
                task.current_step_index += 1
                self.task_manager.persist_task(task)
                task = self.task_manager.set_current_step_index(
                    task.task_id, task.current_step_index
                )
            else:
                err_msg = (
                    "; ".join(verification.failure_reasons)
                    or result.error
                    or "Verification criteria failed"
                )
                task, should_retry = self.recovery.handle_step_failure(
                    task=task,
                    step=step,
                    error=err_msg,
                    task_manager=self.task_manager,
                )
                if not should_retry:
                    return task

        # Phase 3: Final verification and completion
        latest_task = self.task_manager.get_task(task_id)
        if not latest_task:
            return task
        task = latest_task

        if task.status == TaskStatus.RUNNING and task.current_step_index >= len(task.plan):
            task = self.task_manager.transition_task(
                task_id, TaskStatus.VERIFYING, reason="Starting final task verification"
            )
            final_ver = self.verifier.verify_task(task, workspace_path=task.workspace_path)
            if final_ver.verified:
                task = self.task_manager.complete_task(task_id)
            else:
                task = self.task_manager.fail_task(
                    task_id,
                    reason=f"Final task plan verification failed: {'; '.join(final_ver.failure_reasons)}",
                )

        return task
