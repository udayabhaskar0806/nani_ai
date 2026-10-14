"""N.A.N.I. V2 — Tool Registry & Base Tool Interface
Central registry for all native tools with deterministic duplicate prevention,
capability routing discovery, security gating, and journaled execution.
"""

import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from nani.core.context import ExecutionContext
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
        """Validates parameters against schema including required fields, types, and enums."""
        schema = self.parameters_schema
        required = schema.get("required", [])
        for req in required:
            if req not in params:
                return f"Missing required parameter '{req}'"

        properties = schema.get("properties", {})
        for param_name, param_val in params.items():
            if param_name in properties:
                prop_spec = properties[param_name]
                expected_type = prop_spec.get("type")
                if expected_type == "integer" and (
                    not isinstance(param_val, int) or isinstance(param_val, bool)
                ):
                    return f"Parameter '{param_name}' must be an integer, got {type(param_val).__name__}"
                elif expected_type == "number" and (
                    not isinstance(param_val, (int, float)) or isinstance(param_val, bool)
                ):
                    return (
                        f"Parameter '{param_name}' must be a number, got {type(param_val).__name__}"
                    )
                elif expected_type == "string" and not isinstance(param_val, str):
                    return (
                        f"Parameter '{param_name}' must be a string, got {type(param_val).__name__}"
                    )
                elif expected_type == "boolean" and not isinstance(param_val, bool):
                    return f"Parameter '{param_name}' must be a boolean, got {type(param_val).__name__}"
                elif expected_type == "array" and not isinstance(param_val, (list, tuple)):
                    return (
                        f"Parameter '{param_name}' must be an array, got {type(param_val).__name__}"
                    )

                enums = prop_spec.get("enum")
                if enums and param_val not in enums:
                    return f"Parameter '{param_name}' must be one of {enums}, got '{param_val}'"

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
        context: ExecutionContext | None = None,
    ) -> ToolResult:
        """Executes tool through deterministic security gating and execution journaling.

        Enforces:
        1. Reject workspace escape overrides and reserved injection keys
        2. Locate tool
        3. Validate parameters against typed schema
        4. Evaluate SecurityPolicy
        5. Deduplicate and record approval request when HIGH
        6. Record action start
        7. Execute tool with trusted ExecutionContext
        8. Catch structured failures
        9. Record bounded complete ToolResult
        10. Return ToolResult
        """
        active_journal = journal or self.journal
        raw_params = dict(parameters or {})

        # 1. Reserved parameter and workspace override protection (F01)
        for reserved in ("context", "execution_context", "safe_cwd"):
            if reserved in raw_params:
                return ToolResult.fail(
                    error=f"Parameter injection rejected: reserved parameter '{reserved}' cannot be supplied by untrusted action caller."
                )

        if "workspace_path" in raw_params or "workspace" in raw_params:
            passed_ws_val = raw_params.pop("workspace_path", None) or raw_params.pop(
                "workspace", None
            )
            passed_ws = Path(passed_ws_val).resolve()
            if context and context.workspace and passed_ws != context.workspace:
                return ToolResult.fail(
                    error=f"Workspace override rejected: action attempted to escape authorized workspace '{context.workspace}' to '{passed_ws}'."
                )
            if not context:
                context = ExecutionContext(
                    task_id=task_id or "",
                    workspace=passed_ws,
                    step_id=step_id,
                )

        # 2. Locate tool
        tool = self.get(name)
        if not tool:
            return ToolResult.fail(error=f"Tool '{name}' not found in registry.")

        # 3. Validate parameters against typed schema
        val_error = tool.validate_parameters(raw_params)
        if val_error:
            return ToolResult.fail(error=f"Parameter validation failed for '{name}': {val_error}")

        # 4. Evaluate SecurityPolicy
        effective_risk = SecurityPolicy.evaluate_risk(
            tool_name=tool.name,
            parameters=raw_params,
            base_risk=tool.risk_level,
        )

        # 5. Block/return approval requirement when HIGH
        if SecurityPolicy.requires_human_approval(effective_risk):
            if active_journal and task_id:
                active_journal.record_approval_request(
                    task_id=task_id,
                    step_id=step_id,
                    action_description=f"Tool '{name}' with params: {raw_params}",
                    risk_level=effective_risk,
                )
                blocked_act_id = active_journal.record_action_start(
                    task_id=task_id,
                    step_id=step_id,
                    worker=worker,
                    tool=name,
                    parameters=raw_params,
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

        # 6. Record action start
        act_id: str | None = None
        if active_journal and task_id:
            act_id = active_journal.record_action_start(
                task_id=task_id,
                step_id=step_id,
                worker=worker,
                tool=name,
                parameters=raw_params,
            )

        # 7. Execute tool with trusted ExecutionContext
        t_start = time.time()
        result: ToolResult
        try:
            exec_kwargs = dict(raw_params)
            if context:
                exec_kwargs["context"] = context
            result = await tool.run(**exec_kwargs)
        except Exception as e:
            # 8. Catch structured failures
            duration_ms = int((time.time() - t_start) * 1000)
            result = ToolResult.fail(
                error=f"Tool execution exception in '{name}': {e}",
                duration_ms=duration_ms,
            )

        # Ensure duration_ms is populated
        if not result.duration_ms:
            result.duration_ms = int((time.time() - t_start) * 1000)

        # 9. Record full bounded result payload in journal
        if active_journal and act_id:
            act_status = ActionStatus.SUCCESS if result.success else ActionStatus.FAILED
            res_payload = dict(result.data)
            if result.exit_code is not None:
                res_payload["exit_code"] = result.exit_code
            if result.stdout:
                res_payload["stdout"] = result.stdout[:50_000]
            if result.stderr:
                res_payload["stderr"] = result.stderr[:50_000]

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

        # 10. Return ToolResult
        return result
