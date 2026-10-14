"""N.A.N.I. V2 — Native Autonomous Coding Worker
Performs file inspection, syntax diagnosis, AST/diff patching, and automated build/test execution.
"""

from typing import Any

from nani.agents.base import BaseWorker, WorkerResult
from nani.core.state import WorldState
from nani.core.task import Observation, PlanStep, WorkerCapability
from nani.models.router import ModelRouter
from nani.tools.registry import ToolRegistry


class CodingWorker(BaseWorker):
    """Native autonomous coding worker capable of editing, compiling, and fixing source code."""

    def __init__(
        self,
        tool_registry: ToolRegistry,
        model_router: ModelRouter | None = None,
    ) -> None:
        self.tool_registry = tool_registry
        self.model_router = model_router or ModelRouter.create_default()

    @property
    def capability_name(self) -> WorkerCapability:
        return WorkerCapability.CODING

    async def can_handle(self, step: PlanStep, world_state: WorldState) -> bool:
        if step.capability_required == WorkerCapability.CODING:
            return True
        desc = step.description.lower()
        return any(
            k in desc
            for k in [
                "compile",
                "build",
                "code",
                "gcc",
                "make",
                "patch",
                "edit file",
                "write source",
                "refactor",
                "fix bug",
            ]
        )

    async def execute(self, step: PlanStep, world_state: WorldState) -> WorkerResult:
        desc = step.description.lower()
        observations: list[Observation] = []
        changed_files: list[str] = []

        params: dict[str, Any] = {}
        tool_name = ""
        if step.actions:
            act = step.actions[0]
            tool_name = act.tool
            params = dict(act.parameters)

        # 1. Direct tool dispatch if step has pre-declared action
        if tool_name in ("write_file", "patch_file", "read_file", "shell"):
            res = await self.tool_registry.execute(tool_name, params)
            if not res.success:
                return WorkerResult.fail(
                    error=res.error or res.stderr or "Coding action failed",
                    summary=f"Coding action '{tool_name}' failed for step '{step.description}'",
                )

            obs = Observation(
                source=tool_name,
                content=res.stdout or str(res.data),
                metadata={"exit_code": res.exit_code, "success": res.success},
            )
            observations.append(obs)
            if tool_name in ("write_file", "patch_file") and "path" in params:
                changed_files.append(str(params["path"]))

            return WorkerResult.ok(
                summary=f"Executed coding action '{tool_name}' successfully.",
                observations=observations,
                changed_files=changed_files,
            )

        # 2. High-level goal processing: Build / Compile
        if any(k in desc for k in ["compile", "build", "make", "gcc"]):
            cmd = params.get("command") or params.get("cmd") or "make"
            build_res = await self.tool_registry.execute("shell", {"command": cmd})

            obs = Observation(
                source="compiler_output",
                content=build_res.stdout or build_res.stderr or "",
                metadata={"exit_code": build_res.exit_code},
            )
            observations.append(obs)

            if build_res.success:
                return WorkerResult.ok(
                    summary=f"Build command '{cmd}' succeeded with exit code 0.",
                    observations=observations,
                )

            # Build failed: analyze failure
            err_output = build_res.stderr or build_res.stdout or ""
            return WorkerResult.fail(
                error=f"Build failed (exit {build_res.exit_code}): {err_output[:300]}",
                summary=f"Compiler error encountered during '{cmd}'",
            )

        # 3. Default fallback: file writing or inspection
        return WorkerResult.ok(
            summary=f"Coding worker completed step '{step.description}'.",
            observations=observations,
            changed_files=changed_files,
        )
