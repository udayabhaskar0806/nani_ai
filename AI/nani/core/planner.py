"""N.A.N.I. V2 — Autonomous Dynamic Task Planner
Decomposes high-level user goals into structured, verifiable PlanStep sequences.
Uses AI model reasoning when available to dynamically generate multi-step workflows.
Maintains deterministic plan generation for offline testing and verification.
"""

import json
import logging
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
from nani.models.base import ModelCapability, ModelMessage, ModelRequest
from nani.models.router import ModelRouter

logger = logging.getLogger(__name__)


class Planner:
    """Dynamic plan generator producing verifiable PlanStep sequences."""

    C_HELLO_SOURCE = """#include <stdio.h>

int main(void) {
    printf("NANI_PHASE1_OK\\n");
    return 0;
}
"""

    BROKEN_C_SOURCE = """printf("broken")
"""

    def __init__(self, model_router: ModelRouter | None = None) -> None:
        self.model_router = model_router

    async def plan_async(
        self,
        goal: str,
        predefined_steps: list[PlanStep] | None = None,
        task_metadata: dict[str, Any] | None = None,
    ) -> list[PlanStep]:
        """Dynamically generates an execution plan using AI model reasoning when available,
        or falls back to deterministic planning for offline verification.
        """
        if predefined_steps:
            return self._validate_predefined_steps(predefined_steps)

        if "unrecognized" in goal.lower() or "unsupported" in goal.lower():
            raise ValueError(
                f"UNSUPPORTED_GOAL: Objective '{goal}' is not supported in deterministic planner."
            )

        # 1. Attempt dynamic planning via configured ModelRouter
        if self.model_router:
            provider = self.model_router.get_provider_for_capability(
                ModelCapability.REASONING
            ) or self.model_router.get_provider_for_capability(ModelCapability.FAST)
            if provider and await provider.is_available():
                try:
                    dynamic_steps = await self._generate_dynamic_plan(goal, provider, task_metadata)
                    if dynamic_steps:
                        return dynamic_steps
                except Exception as exc:
                    logger.warning(
                        "Dynamic planning failed, falling back to deterministic: %s", exc
                    )

        # 2. Deterministic baseline fallback for testing / offline
        return self.plan(goal=goal, predefined_steps=predefined_steps, task_metadata=task_metadata)

    def _validate_predefined_steps(self, predefined_steps: list[PlanStep]) -> list[PlanStep]:
        steps: list[PlanStep] = []
        for idx, s in enumerate(predefined_steps, start=1):
            if len(s.actions) > 1:
                raise ValueError(
                    f"Step {s.order} has {len(s.actions)} actions. Phase 1 requires exactly one executable action per step."
                )
            s.order = idx
            if not s.step_id:
                s.step_id = str(uuid.uuid4())
            steps.append(s)
        return steps

    async def _generate_dynamic_plan(
        self,
        goal: str,
        provider: Any,
        task_metadata: dict[str, Any] | None = None,
    ) -> list[PlanStep]:
        """Uses AI model reasoning to generate a structured PlanStep sequence."""
        system_prompt = (
            "You are N.A.N.I.'s Autonomous Task Planner.\n"
            "Decompose the user's objective into a minimal, logical sequence of actionable execution steps.\n"
            "Allowed Worker Capabilities: CODING, SYSTEM, RESEARCH, BROWSER, COMPUTER\n"
            "Allowed Tools: shell, read_file, write_file, patch_file, list_directory, search_files, web_search, fetch_web_page, process, git, system_hardware\n"
            "Each step must have:\n"
            "- order: integer (1-indexed)\n"
            "- description: string\n"
            "- capability_required: string (e.g. CODING, SYSTEM, RESEARCH)\n"
            "- risk_level: string (LOW, MEDIUM, HIGH)\n"
            "- worker: string (e.g. system_worker, coding_worker, research_worker)\n"
            "- tool: string (e.g. shell, write_file, web_search)\n"
            '- parameters: object with tool arguments (e.g. {"command": "..."})\n'
            '- verification: object (e.g. {"type": "tool_success"} or {"type": "exit_code", "expected": 0})\n\n'
            "Respond ONLY with a valid JSON array of step objects. No markdown wrapping or other text."
        )

        request = ModelRequest(
            capability=ModelCapability.REASONING,
            messages=[ModelMessage(role="user", content=f"Goal: {goal}")],
            system_prompt=system_prompt,
            temperature=0.2,
            max_tokens=2048,
        )

        response = await provider.generate(request)
        content = response.content.strip()
        if content.startswith("```"):
            lines = content.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            content = "\n".join(lines).strip()

        data = json.loads(content)
        if not isinstance(data, list) or not data:
            return []

        steps: list[PlanStep] = []
        for idx, item in enumerate(data, start=1):
            cap_str = str(item.get("capability_required", "SYSTEM")).upper()
            try:
                cap = WorkerCapability(cap_str)
            except ValueError:
                cap = WorkerCapability.SYSTEM

            risk_str = str(item.get("risk_level", "LOW")).upper()
            try:
                risk = RiskLevel(risk_str)
            except ValueError:
                risk = RiskLevel.LOW

            action = Action(
                worker=str(item.get("worker", "system_worker")),
                tool=str(item.get("tool", "shell")),
                parameters=dict(item.get("parameters", {})),
                status=ActionStatus.PENDING,
            )

            step = PlanStep(
                step_id=str(uuid.uuid4()),
                order=idx,
                description=str(item.get("description", f"Step {idx}")),
                capability_required=cap,
                risk_level=risk,
                status=StepStatus.PENDING,
                verification=dict(item.get("verification", {"type": "tool_success"})),
                actions=[action],
            )
            steps.append(step)

        return steps

    def plan(
        self,
        goal: str,
        predefined_steps: list[PlanStep] | None = None,
        task_metadata: dict[str, Any] | None = None,
    ) -> list[PlanStep]:
        """Generates a deterministic plan for the given goal or validates predefined steps."""
        if predefined_steps:
            return self._validate_predefined_steps(predefined_steps)

        meta = task_metadata or {}
        goal_lower = goal.lower()

        # Deterministic Plan: C Project Build & Execution (unit testing & Phase 1 baseline)
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
