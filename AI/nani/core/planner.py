"""N.A.N.I. V2 — Minimal Deterministic Planner
Generates structured, verifiable PlanSteps for task execution without external AI dependencies.
Validates execution mechanics deterministically.
"""

import uuid
from typing import Any

from nani.core.task import (
    Action,
    ActionStatus,
    PlanStep,
    RiskLevel,
    StepStatus,
    WorkerCapability,
)


class Planner:
    """Deterministic plan generator producing verifiable PlanStep sequences."""

    C_HELLO_SOURCE = """#include <stdio.h>

int main(void) {
    printf("NANI_PHASE1_OK\\n");
    return 0;
}
"""

    BROKEN_C_SOURCE = """printf("broken")
"""

    def plan(
        self,
        goal: str,
        predefined_steps: list[PlanStep] | None = None,
        task_metadata: dict[str, Any] | None = None,
    ) -> list[PlanStep]:
        """Generates a deterministic plan for the given goal."""
        if predefined_steps:
            steps: list[PlanStep] = []
            for idx, s in enumerate(predefined_steps, start=1):
                s.order = idx
                if not s.step_id:
                    s.step_id = str(uuid.uuid4())
                steps.append(s)
            return steps

        meta = task_metadata or {}
        goal_lower = goal.lower()

        # Deterministic Plan: C Project Build & Execution
        if "c project" in goal_lower or "hello.c" in goal_lower or "compile" in goal_lower:
            is_broken = meta.get("broken_syntax", False) or "broken" in goal_lower
            c_code = self.BROKEN_C_SOURCE if is_broken else self.C_HELLO_SOURCE

            step1 = PlanStep(
                order=1,
                description="Inspect workspace directory",
                capability_required=WorkerCapability.SYSTEM,
                risk_level=RiskLevel.LOW,
                status=StepStatus.PENDING,
                verification={"type": "tool_success"},
                actions=[
                    Action(
                        worker="system_worker",
                        tool="list_directory",
                        parameters={"path": "."},
                        status=ActionStatus.PENDING,
                    )
                ],
            )

            step2 = PlanStep(
                order=2,
                description="Create hello.c source file",
                capability_required=WorkerCapability.CODING,
                risk_level=RiskLevel.MEDIUM,
                status=StepStatus.PENDING,
                verification={
                    "type": "file_content",
                    "path": "hello.c",
                    "expected_content": c_code,
                },
                actions=[
                    Action(
                        worker="coding_worker",
                        tool="write_file",
                        parameters={"path": "hello.c", "content": c_code},
                        status=ActionStatus.PENDING,
                    )
                ],
            )

            step3 = PlanStep(
                order=3,
                description="Compile C source: gcc hello.c -o hello",
                capability_required=WorkerCapability.CODING,
                risk_level=RiskLevel.MEDIUM,
                status=StepStatus.PENDING,
                verification={"type": "exit_code", "expected": 0},
                actions=[
                    Action(
                        worker="coding_worker",
                        tool="shell",
                        parameters={"command": "gcc hello.c -o hello"},
                        status=ActionStatus.PENDING,
                    )
                ],
            )

            step4 = PlanStep(
                order=4,
                description="Execute compiled binary: ./hello",
                capability_required=WorkerCapability.CODING,
                risk_level=RiskLevel.MEDIUM,
                status=StepStatus.PENDING,
                verification={"type": "stdout_contains", "expected": "NANI_PHASE1_OK"},
                actions=[
                    Action(
                        worker="coding_worker",
                        tool="shell",
                        parameters={"command": "./hello"},
                        status=ActionStatus.PENDING,
                    )
                ],
            )

            return [step1, step2, step3, step4]

        # Generic single-step fallback plan
        return [
            PlanStep(
                order=1,
                description=f"Execute deterministic task: {goal}",
                capability_required=WorkerCapability.SYSTEM,
                risk_level=RiskLevel.LOW,
                status=StepStatus.PENDING,
                verification={"type": "tool_success"},
                actions=[
                    Action(
                        worker="system_worker",
                        tool="shell",
                        parameters={"command": meta.get("command", "echo 'NANI_OK'")},
                        status=ActionStatus.PENDING,
                    )
                ],
            )
        ]
