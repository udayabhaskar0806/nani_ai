"""N.A.N.I. V2 — Tool Registry & Base Tool Interface
Central registry for all native tools with deterministic duplicate prevention.
"""

from abc import ABC, abstractmethod
from typing import Any

from nani.core.task import RiskLevel
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
    def parameters_schema(self) -> dict[str, Any]:
        """JSON schema describing acceptable arguments."""
        return {}

    @abstractmethod
    async def run(self, **kwargs: Any) -> ToolResult:
        """Executes the tool with arguments and returns a standardized ToolResult."""
        pass


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

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

    def list_tools(self) -> dict[str, BaseTool]:
        return dict(self._tools)

    def get_schemas(self) -> dict[str, Any]:
        return {
            name: {
                "description": tool.description,
                "risk_level": tool.risk_level.value,
                "parameters": tool.parameters_schema,
            }
            for name, tool in self._tools.items()
        }
