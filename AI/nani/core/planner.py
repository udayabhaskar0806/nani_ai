"""N.A.N.I. V2 — Minimal Deterministic Planner
Generates structured, verifiable PlanSteps for task execution without external AI dependencies.
Strictly rejects unsupported goals instead of completing via fake fallbacks.
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
        """Generates a deterministic plan for the given goal or validates predefined steps."""
        if predefined_steps:
            steps: list[PlanStep] = []
            for idx, s in enumerate(predefined_steps, start=1):
                # Phase 1 invariant: exactly one executable action per step
                if len(s.actions) > 1:
                    raise ValueError(
                        f"Step {s.order} has {len(s.actions)} actions. Phase 1 requires exactly one executable action per step."
                    )
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

        # Research Goal: Autonomous web search and knowledge synthesis
        if any(
            k in goal_lower for k in ("research", "search", "lookup", "find out", "google", "ddg")
        ):
            step = PlanStep(
                order=1,
                description=goal,
                capability_required=WorkerCapability.RESEARCH,
                risk_level=RiskLevel.LOW,
                status=StepStatus.PENDING,
                verification={"type": "tool_success"},
                actions=[
                    Action(
                        worker="research_worker",
                        tool="web_search",
                        parameters={"query": goal},
                        status=ActionStatus.PENDING,
                    )
                ],
            )
            return [step]

        # System Hardware Telemetry Goal
        if any(
            k in goal_lower
            for k in (
                "hardware",
                "battery",
                "system resources",
                "ram",
                "cpu load",
                "audio volume",
                "system info",
            )
        ):
            op = "get_system_resources"
            if "battery" in goal_lower:
                op = "get_battery"
            elif "volume" in goal_lower:
                op = "get_volume"

            step = PlanStep(
                order=1,
                description=goal,
                capability_required=WorkerCapability.SYSTEM,
                risk_level=RiskLevel.LOW,
                status=StepStatus.PENDING,
                verification={"type": "tool_success"},
                actions=[
                    Action(
                        worker="system_worker",
                        tool="system_hardware",
                        parameters={"operation": op},
                        status=ActionStatus.PENDING,
                    )
                ],
            )
            return [step]

        # Explicit goal rejection: Do NOT complete unsupported objectives with echo fallback
        raise ValueError(
            f"UNSUPPORTED_GOAL: Objective '{goal}' is not supported in deterministic planner."
        )
