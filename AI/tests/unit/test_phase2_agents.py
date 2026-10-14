"""Unit tests for Phase 2 specialized autonomous agent workers."""

from pathlib import Path

import pytest

from nani.agents.coding.native import CodingWorker
from nani.agents.computer.native_linux import ComputerWorker
from nani.agents.research.native import ResearchWorker
from nani.core.state import WorldState
from nani.core.task import Action, PlanStep, WorkerCapability
from nani.memory.database import Database
from nani.models.base import ModelCapability, ModelProvider, ModelRequest, ModelResponse
from nani.models.router import ModelRouter
from nani.tools.filesystem import register_filesystem_tools
from nani.tools.registry import BaseTool, ToolRegistry
from nani.tools.result import ToolResult


@pytest.fixture
def test_registry(tmp_path: Path) -> ToolRegistry:
    reg = ToolRegistry()
    register_filesystem_tools(reg, tmp_path)
    return reg


@pytest.mark.asyncio
async def test_coding_worker_can_handle_and_execute(test_registry: ToolRegistry, tmp_path: Path):
    worker = CodingWorker(test_registry)
    assert worker.capability_name == WorkerCapability.CODING

    step = PlanStep(
        order=1,
        description="Write a hello.py script",
        capability_required=WorkerCapability.CODING,
        actions=[
            Action(
                worker="coding_worker",
                tool="write_file",
                parameters={"path": "hello.py", "content": "print('hello')"},
            )
        ],
    )

    can_do = await worker.can_handle(step, WorldState())
    assert can_do is True

    result = await worker.execute(step, WorldState())
    assert result.success is True
    assert "hello.py" in result.changed_files
    assert (tmp_path / "hello.py").read_text() == "print('hello')"


@pytest.mark.asyncio
async def test_research_worker_execution_with_mocked_search(tmp_path: Path):
    reg = ToolRegistry()

    # Mock web search tool returning synthetic findings
    class MockSearchTool(BaseTool):
        @property
        def name(self) -> str:
            return "web_search"

        @property
        def description(self) -> str:
            return "mock search"

        @property
        def risk_level(self):
            from nani.core.task import RiskLevel

            return RiskLevel.LOW

        async def run(self, **kwargs):
            return ToolResult.ok(
                data={
                    "results": [
                        {
                            "title": "Python Concurrency Guide",
                            "url": "https://example.com/concurrency",
                            "snippet": "Asyncio uses an event loop for cooperative multitasking.",
                        }
                    ]
                }
            )

    reg.register(MockSearchTool())
    db = Database(tmp_path / "research_test.db")
    empty_router = ModelRouter()
    worker = ResearchWorker(tool_registry=reg, model_router=empty_router, db=db)

    assert worker.capability_name == WorkerCapability.RESEARCH

    step = PlanStep(
        order=1,
        description="Research asyncio event loops",
        capability_required=WorkerCapability.RESEARCH,
    )

    can_do = await worker.can_handle(step, WorldState())
    assert can_do is True

    result = await worker.execute(step, WorldState())
    assert result.success is True
    assert "Python Concurrency Guide" in result.summary
    assert len(result.observations) >= 1

    # Verify memory was updated in SQLite database
    with db.get_connection() as conn:
        cur = conn.execute("SELECT * FROM episodic_memory WHERE error_pattern LIKE '%RESEARCH%'")
        row = cur.fetchone()
        assert row is not None
        assert "cooperative multitasking" in row["solution_summary"]


@pytest.mark.asyncio
async def test_computer_worker_can_handle():
    worker = ComputerWorker()
    assert worker.capability_name == WorkerCapability.COMPUTER

    step = PlanStep(
        order=1,
        description="Click at screen coordinates",
        capability_required=WorkerCapability.COMPUTER,
    )

    can_do = await worker.can_handle(step, WorldState())
    assert can_do is True


@pytest.mark.asyncio
async def test_research_worker_with_mocked_model_provider(tmp_path: Path):
    reg = ToolRegistry()

    class MockSearchTool(BaseTool):
        @property
        def name(self) -> str:
            return "web_search"

        @property
        def description(self) -> str:
            return "mock search"

        @property
        def risk_level(self):
            from nani.core.task import RiskLevel

            return RiskLevel.LOW

        async def run(self, **kwargs):
            return ToolResult.ok(
                data={
                    "results": [
                        {
                            "title": "Quantum Computing",
                            "url": "https://example.com/quantum",
                            "snippet": "Qubits exist in superposition states.",
                        }
                    ]
                }
            )

    class MockAIProvider(ModelProvider):
        @property
        def name(self) -> str:
            return "mock_ai"

        @property
        def supported_capabilities(self) -> list[ModelCapability]:
            return [ModelCapability.RESEARCH]

        async def is_available(self) -> bool:
            return True

        async def generate(self, request: ModelRequest) -> ModelResponse:
            return ModelResponse(
                content="Synthesized insight: Qubits enable quantum parallelism.",
                provider_name="mock_ai",
                model_name="mock_ai_v1",
                tokens_used=42,
            )

    reg.register(MockSearchTool())
    router = ModelRouter()
    router.register_provider(MockAIProvider())
    db = Database(tmp_path / "research_ai_test.db")
    worker = ResearchWorker(tool_registry=reg, model_router=router, db=db)

    step = PlanStep(
        order=1,
        description="Explain quantum superposition",
        capability_required=WorkerCapability.RESEARCH,
    )

    result = await worker.execute(step, WorldState())
    assert result.success is True
    assert "quantum parallelism" in result.summary
    assert len(result.observations) >= 1

    with db.get_connection() as conn:
        cur = conn.execute("SELECT * FROM episodic_memory WHERE error_pattern LIKE '%RESEARCH%'")
        row = cur.fetchone()
        assert row is not None
        assert "quantum parallelism" in row["solution_summary"]
