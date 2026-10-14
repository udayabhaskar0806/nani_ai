"""N.A.N.I. V2 — Minimal Autonomous Runtime Orchestrator
Coordinates TaskManager, Planner, CapabilityRouter, ToolRegistry, Verifier, and Recovery.
Maintains interruptibility and enforces strict state transitions without direct database or subprocess access.
"""

from typing import Any

from nani.core.planner import Planner
from nani.core.recovery import RecoveryManager
from nani.core.router import CapabilityRouter
from nani.core.task import PlanStep, StepStatus, Task, TaskStatus
from nani.core.task_manager import TaskManager
from nani.core.verifier import Verifier
from nani.memory.journal import ActionJournal
from nani.tools.registry import ToolRegistry


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

        CREATED -> PLANNING -> RUNNING -> VERIFYING -> COMPLETED
        Handles WAITING, PAUSED, and RECOVERY paths cleanly.
        """
        task = self.task_manager.get_task(task_id)
        if not task:
            raise KeyError(f"Task '{task_id}' not found.")

        # Phase 1: Planning initialization
        if task.status == TaskStatus.CREATED:
            task = self.task_manager.transition_task(
                task_id, TaskStatus.PLANNING, reason="Generating task execution plan"
            )
            plan = self.planner.plan(
                goal=task.original_goal,
                predefined_steps=predefined_steps,
                task_metadata=task.metadata,
            )
            task = self.task_manager.update_plan(task_id, plan)
            task = self.task_manager.transition_task(
                task_id, TaskStatus.RUNNING, reason="Starting plan execution"
            )

        elif task.status == TaskStatus.PAUSED:
            task = self.task_manager.resume_task(task_id)

        elif task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
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

            if "workspace_path" not in params:
                params["workspace_path"] = task.workspace_path

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
            )

            # Security gate: High risk requires human creator approval -> WAITING
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
                # If retryable, loop re-executes current step

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
                    task_id, reason="Final task plan verification failed"
                )

        return task
