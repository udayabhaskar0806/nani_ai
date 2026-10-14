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

    def route(self, step: PlanStep, world_state: WorldState | None = None) -> RoutingDecision:
        cap = step.capability_required
        desc = step.description.lower()

        if cap == WorkerCapability.CODING:
            worker = "coding_worker"
            if any(k in desc for k in ["write", "create file", "create hello", "save"]):
                suggested_tool = "write_file"
            elif any(k in desc for k in ["read", "view", "inspect file"]):
                suggested_tool = "read_file"
            elif any(k in desc for k in ["patch", "edit", "replace", "modify"]):
                suggested_tool = "patch_file"
            elif "git" in desc:
                suggested_tool = "git"
            elif any(k in desc for k in ["compile", "gcc", "build", "make", "execute", "run"]):
                suggested_tool = "shell"
            else:
                suggested_tool = "write_file"

            rationale = f"Deterministic CODING route mapping step '{step.description}' to '{suggested_tool}'."

        elif cap == WorkerCapability.SYSTEM:
            worker = "system_worker"
            if any(k in desc for k in ["process", "kill", "ps", "pid"]):
                suggested_tool = "process"
            elif any(k in desc for k in ["list", "ls", "search", "find", "dir"]):
                suggested_tool = "list_directory"
            else:
                suggested_tool = "shell"

            rationale = f"Deterministic SYSTEM route mapping step '{step.description}' to '{suggested_tool}'."

        else:
            worker = "system_worker"
            suggested_tool = "shell"
            rationale = f"Fallback routing for {cap.value} to '{suggested_tool}'."

        return RoutingDecision(
            capability=cap,
            worker=worker,
            suggested_tool=suggested_tool,
            rationale=rationale,
        )
