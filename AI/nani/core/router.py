"""N.A.N.I. V2 — Capability Router
Deterministic worker and tool capability routing for plan steps.
Routes tasks to specialized native capabilities without model dependency.
"""

from pydantic import BaseModel

from nani.core.state import WorldState
from nani.core.task import PlanStep, WorkerCapability


class RoutingDecision(BaseModel):
    capability: WorkerCapability
    worker: str
    suggested_tool: str
    rationale: str


class CapabilityRouter:
    """Routes plan steps to appropriate native worker and tool capabilities."""

    DEFAULT_TOOL_MAP: dict[WorkerCapability, tuple[str, str]] = {
        WorkerCapability.CODING: ("coding_worker", "write_file"),
        WorkerCapability.SYSTEM: ("system_worker", "shell"),
        WorkerCapability.RESEARCH: ("research_worker", "web_search"),
        WorkerCapability.BROWSER: ("browser_worker", "fetch_web_page"),
        WorkerCapability.COMPUTER: ("computer_worker", "system_hardware"),
    }

    def route(self, step: PlanStep, world_state: WorldState | None = None) -> RoutingDecision:
        cap = step.capability_required

        # 1. If step already specifies an executable action with a designated tool, respect it
        if step.actions and step.actions[0].tool:
            worker = step.actions[0].worker or f"{cap.value.lower()}_worker"
            suggested_tool = step.actions[0].tool
            rationale = f"Preserving designated tool '{suggested_tool}' from plan step."
            return RoutingDecision(
                capability=cap,
                worker=worker,
                suggested_tool=suggested_tool,
                rationale=rationale,
            )

        # 2. General capability routing based on native capability
        default_worker, default_tool = self.DEFAULT_TOOL_MAP.get(cap, ("system_worker", "shell"))
        return RoutingDecision(
            capability=cap,
            worker=default_worker,
            suggested_tool=default_tool,
            rationale=f"Capability routing for {cap.value} to '{default_tool}'.",
        )
