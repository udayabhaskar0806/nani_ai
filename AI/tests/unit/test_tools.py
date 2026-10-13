"""Unit tests for tool registration, duplicate prevention, and schema export."""

from typing import Any

import pytest

from nani.core.task import RiskLevel
from nani.tools.registry import BaseTool, DuplicateToolError, ToolRegistry
from nani.tools.result import ToolResult


class MockTool(BaseTool):
    def __init__(self, tool_name: str = "mock_tool", risk: RiskLevel = RiskLevel.LOW):
        self._name = tool_name
        self._risk = risk

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "A mock tool for testing."

    @property
    def risk_level(self) -> RiskLevel:
        return self._risk

    async def run(self, **kwargs: Any) -> ToolResult:
        return ToolResult.ok(data={"status": "mocked"})


def test_tool_registration():
    registry = ToolRegistry()
    tool = MockTool("read_file")
    registry.register(tool)

    assert registry.get("read_file") is tool
    assert "read_file" in registry.list_tools()


def test_duplicate_tool_registration_rejected():
    registry = ToolRegistry()
    tool1 = MockTool("search_files")
    tool2 = MockTool("search_files")

    registry.register(tool1)
    with pytest.raises(DuplicateToolError, match="already registered"):
        registry.register(tool2)


def test_explicit_tool_replacement():
    registry = ToolRegistry()
    tool1 = MockTool("run_shell", risk=RiskLevel.MEDIUM)
    tool2 = MockTool("run_shell", risk=RiskLevel.HIGH)

    registry.register(tool1)
    assert registry.get("run_shell").risk_level == RiskLevel.MEDIUM

    registry.replace(tool2)
    assert registry.get("run_shell").risk_level == RiskLevel.HIGH


def test_tool_schemas_export():
    registry = ToolRegistry()
    registry.register(MockTool("test_tool", risk=RiskLevel.LOW))

    schemas = registry.get_schemas()
    assert "test_tool" in schemas
    assert schemas["test_tool"]["risk_level"] == "LOW"
