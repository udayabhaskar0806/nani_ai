"""N.A.N.I. V2 — Tool Registry & Base Tool Interface
Central registry for all native tools with deterministic duplicate prevention,
capability routing discovery, security gating, and journaled execution.
"""

import time
from abc import ABC, abstractmethod
from typing import Any

from nani.core.task import ActionStatus, RiskLevel, WorkerCapability
from nani.memory.journal import ActionJournal
from nani.security.policy import SecurityPolicy
from nani.tools.result import ToolResult


class DuplicateToolError(ValueError):
    """Raised when attempting to register a tool with a name that is already registered."""

    pass


class BaseTool(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier of the tool."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Clear description of what the tool does."""
        pass

    @property
    @abstractmethod
    def risk_level(self) -> RiskLevel:
        """Security risk tier (LOW, MEDIUM, HIGH)."""
        pass

    @property
    def capability(self) -> WorkerCapability:
        """Primary worker capability associated with this tool."""
        return WorkerCapability.SYSTEM

    @property
    def parameters_schema(self) -> dict[str, Any]:
        """JSON schema describing acceptable arguments."""
        return {}

    def validate_parameters(self, params: dict[str, Any]) -> str | None:
        """Validates parameters against schema. Returns error string if invalid, None if valid."""
        schema = self.parameters_schema
        required = schema.get("required", [])
        for req in required:
            if req not in params:
                return f"Missing required parameter '{req}'"
        return None

    @abstractmethod
    async def run(self, **kwargs: Any) -> ToolResult:
        """Executes the tool with arguments and returns a standardized ToolResult."""
        pass


class ToolRegistry:
    def __init__(self, journal: ActionJournal | None = None) -> None:
        self._tools: dict[str, BaseTool] = {}
        self.journal = journal

    def register(self, tool: BaseTool) -> None:
        """Registers a tool. Raises DuplicateToolError if a tool with the same name already exists."""
        if tool.name in self._tools:
            raise DuplicateToolError(
                f"Tool '{tool.name}' is already registered. "
                "Use replace() if you intentionally want to override an existing tool."
            )
        self._tools[tool.name] = tool

    def replace(self, tool: BaseTool) -> None:
        """Explicitly overrides an existing tool in the registry."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def exists(self, name: str) -> bool:
        """Checks if a tool with the given name is registered."""
        return name in self._tools

    def list_tools(self) -> dict[str, BaseTool]:
        return dict(self._tools)

    def find_by_capability(self, capability: WorkerCapability | str) -> list[BaseTool]:
        """Returns all registered tools matching the given WorkerCapability."""
        cap_val = capability.value if isinstance(capability, WorkerCapability) else str(capability)
        return [t for t in self._tools.values() if t.capability.value == cap_val]

    def get_schemas(self) -> dict[str, Any]:
        return {
            name: {
                "description": tool.description,
                "risk_level": tool.risk_level.value,
                "capability": tool.capability.value,
                "parameters": tool.parameters_schema,
            }
            for name, tool in self._tools.items()
        }

    async def execute(
        self,
        name: str,
        parameters: dict[str, Any] | None = None,
        task_id: str | None = None,
        step_id: str | None = None,
        worker: str = "SYSTEM",
        journal: ActionJournal | None = None,
    ) -> ToolResult:
        """Executes tool through deterministic security gating and execution journaling.

        Enforces:
        1. locate tool
        2. validate parameters
        3. evaluate SecurityPolicy
        4. block/return approval requirement when HIGH
        5. record action start
        6. execute tool
        7. catch structured failures
        8. record result
        9. return ToolResult
        """
        active_journal = journal or self.journal
        params = parameters or {}

        # 1. Locate tool
        tool = self.get(name)
        if not tool:
            return ToolResult.fail(error=f"Tool '{name}' not found in registry.")

        # 2. Validate parameters
        val_error = tool.validate_parameters(params)
        if val_error:
            return ToolResult.fail(error=f"Parameter validation failed for '{name}': {val_error}")

        # 3. Evaluate SecurityPolicy
        effective_risk = SecurityPolicy.evaluate_risk(
            tool_name=tool.name,
            parameters=params,
            base_risk=tool.risk_level,
        )

        # 4. Block/return approval requirement when HIGH
        if SecurityPolicy.requires_human_approval(effective_risk):
            if active_journal and task_id:
                active_journal.record_approval_request(
                    task_id=task_id,
                    step_id=step_id,
                    action_description=f"Tool '{name}' with params: {params}",
                    risk_level=effective_risk,
                )
                blocked_act_id = active_journal.record_action_start(
                    task_id=task_id,
                    step_id=step_id,
                    worker=worker,
                    tool=name,
                    parameters=params,
                )
                active_journal.record_action_result(
                    action_id=blocked_act_id,
                    status=ActionStatus.BLOCKED,
                    duration_ms=0,
                    error=f"Blocked: High-risk operation '{name}' requires human creator approval",
                    task_id=task_id,
                    step_id=step_id,
                    worker=worker,
                    tool=name,
                )

            return ToolResult.fail(
                error=f"Approval required: operation '{name}' evaluated as HIGH risk.",
                metadata={"approval_required": True, "risk_level": effective_risk.value},
            )

        # 5. Record action start
        act_id: str | None = None
        if active_journal and task_id:
            act_id = active_journal.record_action_start(
                task_id=task_id,
                step_id=step_id,
                worker=worker,
                tool=name,
                parameters=params,
            )

        # 6. Execute tool
        t_start = time.time()
        result: ToolResult
        try:
            result = await tool.run(**params)
        except Exception as e:
            # 7. Catch structured failures
            duration_ms = int((time.time() - t_start) * 1000)
            result = ToolResult.fail(
                error=f"Tool execution exception in '{name}': {e}",
                duration_ms=duration_ms,
            )

        # Ensure duration_ms is populated
        if not result.duration_ms:
            result.duration_ms = int((time.time() - t_start) * 1000)

        # 8. Record result
        if active_journal and act_id:
            act_status = ActionStatus.SUCCESS if result.success else ActionStatus.FAILED
            res_payload = dict(result.data)
            if result.exit_code is not None:
                res_payload["exit_code"] = result.exit_code
            if result.stdout:
                res_payload["stdout"] = result.stdout
            active_journal.record_action_result(
                action_id=act_id,
                status=act_status,
                duration_ms=result.duration_ms,
                result=res_payload,
                error=result.error or (result.stderr if not result.success else None),
                task_id=task_id,
                step_id=step_id,
                worker=worker,
                tool=name,
            )

        # 9. Return ToolResult
        return result
