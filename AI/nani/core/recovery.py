"""N.A.N.I. V2 — Recovery Skeleton & Retry Engine
Provides deterministic failure classification, retry enforcement, and lifecycle state transitions.
Guarantees clean termination without infinite loops.
"""

from typing import Any

from nani.core.task import PlanStep, StepStatus, Task, TaskStatus
from nani.core.task_manager import TaskManager


class RecoveryManager:
    """Manages failure handling, retry evaluation, and recovery transitions."""

    NON_RETRYABLE_PATTERNS = [
        "approval required",
        "human creator approval",
        "outside authorized workspace",
        "access denied: path",
        "permission denied: path",
    ]

    def is_retryable(self, error: str | None) -> bool:
        """Determines if the failure is eligible for automated retry."""
        if not error:
            return True
        err_lower = error.lower()
        for pattern in self.NON_RETRYABLE_PATTERNS:
            if pattern in err_lower:
                return False
        return True

    def handle_step_failure(
        self,
        task: Task,
        step: PlanStep,
        error: str,
        task_manager: TaskManager,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[Task, bool]:
        """Handles a step execution or verification failure.

        Evaluates retry eligibility:
        - If retryable and step.retry_count < step.max_retries:
            transitions RUNNING -> RECOVERY -> RUNNING and increments retry_count.
            Returns (task, True).
        - If not retryable or retries exhausted:
            transitions RUNNING -> RECOVERY -> FAILED and marks step FAILED.
            Returns (task, False).
        """
        retryable = self.is_retryable(error)

        # Transition task to RECOVERY
        task = task_manager.transition_task(
            task.task_id,
            TaskStatus.RECOVERY,
            reason=f"Step {step.order} failed: {error}",
        )

        # Find step in the reloaded task model
        target_step = next((s for s in task.plan if s.step_id == step.step_id), step)

        if retryable and target_step.retry_count < target_step.max_retries:
            target_step.retry_count += 1
            step.retry_count = target_step.retry_count
            target_step.status = StepStatus.IN_PROGRESS
            step.status = StepStatus.IN_PROGRESS
            target_step.error = error
            step.error = error
            task_manager.persist_task(task)

            # Transition RECOVERY -> RUNNING to attempt retry
            task = task_manager.transition_task(
                task.task_id,
                TaskStatus.RUNNING,
                reason=f"Retrying step {target_step.order} (attempt {target_step.retry_count}/{target_step.max_retries})",
            )
            return task, True
        else:
            target_step.status = StepStatus.FAILED
            step.status = StepStatus.FAILED
            target_step.error = error
            step.error = error
            task_manager.persist_task(task)

            # Terminal transition RECOVERY -> FAILED
            fail_reason = (
                f"Step {target_step.order} ('{target_step.description}') failed: max retries ({target_step.max_retries}) reached. Error: {error}"
                if target_step.retry_count >= target_step.max_retries
                else f"Step {target_step.order} ('{target_step.description}') encountered non-retryable error: {error}"
            )
            task = task_manager.fail_task(task.task_id, reason=fail_reason)
            return task, False
