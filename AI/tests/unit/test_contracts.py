"""Unit tests for Phase 0 core contracts and data models."""

from nani.agents.base import WorkerResult
from nani.core.task import Observation, PlanStep, RiskLevel, Task, TaskStatus
from nani.models.base import ModelCapability
from nani.security.policy import SecurityPolicy
from nani.tools.result import ToolResult


def test_task_status_enum():
    assert TaskStatus.CREATED == "CREATED"
    assert TaskStatus.RUNNING == "RUNNING"
    assert TaskStatus.COMPLETED == "COMPLETED"
    assert TaskStatus.FAILED == "FAILED"
    assert TaskStatus.WAITING == "WAITING"


def test_risk_level_enum():
    assert RiskLevel.LOW == "LOW"
    assert RiskLevel.MEDIUM == "MEDIUM"
    assert RiskLevel.HIGH == "HIGH"


def test_model_capability_enum():
    assert ModelCapability.FAST == "FAST"
    assert ModelCapability.REASONING == "REASONING"
    assert ModelCapability.CODING == "CODING"
    assert ModelCapability.VISION == "VISION"
    assert ModelCapability.RESEARCH == "RESEARCH"
    assert ModelCapability.VERIFICATION == "VERIFICATION"


def test_task_serialization_roundtrip():
    step = PlanStep(order=1, description="Inspect project Makefile", capability_required="system")
    task = Task(
        original_goal="Build embedded driver",
        interpreted_goal="Fix SPI driver build error",
        status=TaskStatus.PLANNING,
        risk_level=RiskLevel.LOW,
        plan=[step],
    )

    json_str = task.model_dump_json()
    reconstructed = Task.model_validate_json(json_str)

    assert reconstructed.task_id == task.task_id
    assert reconstructed.original_goal == "Build embedded driver"
    assert len(reconstructed.plan) == 1
    assert reconstructed.plan[0].description == "Inspect project Makefile"


def test_tool_result_ok():
    res = ToolResult.ok(data={"exit_code": 0}, stdout="Build succeeded", duration_ms=120)
    assert res.success is True
    assert res.exit_code == 0
    assert res.stdout == "Build succeeded"
    assert res.duration_ms == 120
    assert res.error is None


def test_tool_result_fail():
    res = ToolResult.fail(error="File not found", stderr="No such file or directory", exit_code=2)
    assert res.success is False
    assert res.error == "File not found"
    assert res.exit_code == 2


def test_worker_result_serialization():
    obs = Observation(source="stdout", content="make: *** [all] Error 2")
    res = WorkerResult.ok(
        summary="Build failed with compiler error", observations=[obs], changed_files=["src/spi.c"]
    )
    assert res.success is True
    assert len(res.observations) == 1
    assert res.observations[0].content == "make: *** [all] Error 2"
    assert res.changed_files == ["src/spi.c"]


def test_security_policy_evaluation():
    # Low risk
    assert SecurityPolicy.evaluate_risk("read_file", {"path": "main.c"}) == RiskLevel.LOW
    assert SecurityPolicy.requires_human_approval(RiskLevel.LOW) is False

    # Medium risk
    assert SecurityPolicy.evaluate_risk("write_file", {"path": "main.c"}) == RiskLevel.MEDIUM
    assert SecurityPolicy.requires_human_approval(RiskLevel.MEDIUM) is False

    # High risk
    assert SecurityPolicy.evaluate_risk("checkout", {"action": "payment_upi"}) == RiskLevel.HIGH
    assert SecurityPolicy.evaluate_risk("bash", {"cmd": "rm -rf /"}) == RiskLevel.HIGH
    assert SecurityPolicy.requires_human_approval(RiskLevel.HIGH) is True
