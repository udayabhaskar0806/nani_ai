"""Hardened unit tests for Phase 0 core contracts, validation, and enums."""

import time
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from nani.config import Config
from nani.core.state import DesktopState, WorldState
from nani.core.task import (
    Action,
    ActionStatus,
    PlanStep,
    RiskLevel,
    Task,
    TaskStatus,
    WorkerCapability,
)
from nani.security.policy import SecurityPolicy
from nani.tools.result import ToolResult


def test_task_status_enum():
    assert TaskStatus.CREATED == "CREATED"
    assert TaskStatus.RUNNING == "RUNNING"
    assert TaskStatus.COMPLETED == "COMPLETED"
    assert TaskStatus.FAILED == "FAILED"
    assert TaskStatus.WAITING == "WAITING"


def test_invalid_task_status_rejected():
    with pytest.raises(ValidationError):
        Task(original_goal="Build", status="INVALID_STATUS")  # type: ignore[arg-type]


def test_risk_level_enum():
    assert RiskLevel.LOW == "LOW"
    assert RiskLevel.MEDIUM == "MEDIUM"
    assert RiskLevel.HIGH == "HIGH"


def test_invalid_risk_level_rejected():
    with pytest.raises(ValidationError):
        PlanStep(
            order=1,
            description="Run",
            capability_required=WorkerCapability.SYSTEM,
            risk_level="CRITICAL",  # type: ignore[arg-type]
        )


def test_worker_capability_enum():
    assert WorkerCapability.CODING == "CODING"
    assert WorkerCapability.BROWSER == "BROWSER"
    assert WorkerCapability.COMPUTER == "COMPUTER"
    assert WorkerCapability.SYSTEM == "SYSTEM"
    assert WorkerCapability.RESEARCH == "RESEARCH"


def test_invalid_worker_capability_rejected():
    with pytest.raises(ValidationError):
        PlanStep(
            order=1,
            description="Run step",
            capability_required="UNRESTRICTED_STRING",  # type: ignore[arg-type]
        )


def test_action_status_enum():
    assert ActionStatus.PENDING == "PENDING"
    assert ActionStatus.RUNNING == "RUNNING"
    assert ActionStatus.SUCCESS == "SUCCESS"
    assert ActionStatus.FAILED == "FAILED"
    assert ActionStatus.BLOCKED == "BLOCKED"
    assert ActionStatus.CANCELLED == "CANCELLED"


def test_invalid_action_status_rejected():
    with pytest.raises(ValidationError):
        Action(worker="system", tool="shell", status="UNKNOWN_STATUS")  # type: ignore[arg-type]


def test_tool_result_without_exit_code():
    # Filesystem / GUI / API tools do not return process exit codes
    res = ToolResult.ok(data={"bytes_read": 1024})
    assert res.success is True
    assert res.exit_code is None
    assert res.data["bytes_read"] == 1024


def test_tool_result_shell_exit_code():
    # Shell / process tools explicitly populate exit_code
    res = ToolResult.ok(stdout="make: target up to date", exit_code=0, duration_ms=45)
    assert res.success is True
    assert res.exit_code == 0
    assert res.duration_ms == 45

    res_fail = ToolResult.fail(error="Command failed", stderr="Segmentation fault", exit_code=139)
    assert res_fail.success is False
    assert res_fail.exit_code == 139
    assert res_fail.stderr == "Segmentation fault"


def test_task_workspace_not_hardcoded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    # Verify default workspace dynamically binds to Path.cwd(), not a hardcoded machine path
    monkeypatch.chdir(tmp_path)
    task_default = Task(original_goal="Explore codebase")
    assert task_default.workspace_path == str(tmp_path)
    assert "/home/dell/Vibe Coding" not in str(tmp_path)

    task_custom = Task(original_goal="Build", workspace_path="/srv/projects/c_driver")
    assert task_custom.workspace_path == "/srv/projects/c_driver"


def test_desktop_resolution_not_hardcoded():
    desktop = DesktopState()
    assert desktop.screen_resolution == "unknown"
    assert "3072" not in desktop.screen_resolution


def test_worldstate_real_timestamp():
    t_before = time.time()
    state = WorldState()
    t_after = time.time()
    assert state.timestamp >= t_before
    assert state.timestamp <= t_after
    assert state.timestamp > 0.0


def test_config_masks_secrets():
    # SecretStr must not reveal API keys in repr or str
    raw_secret = "super_secret_api_key_12345"
    cfg = Config(gemini_api_key=SecretStr(raw_secret))

    config_str = str(cfg)
    config_repr = repr(cfg)

    assert raw_secret not in config_str
    assert raw_secret not in config_repr
    assert "**********" in config_repr
    assert cfg.get_secret("gemini_api_key") == raw_secret


def test_structured_security_policy():
    # 1. Base low risk
    assert (
        SecurityPolicy.evaluate_risk("read_file", {"path": "main.c"}, base_risk=RiskLevel.LOW)
        == RiskLevel.LOW
    )

    # 2. Base medium risk
    assert (
        SecurityPolicy.evaluate_risk("patch_file", {"path": "main.c"}, base_risk=RiskLevel.MEDIUM)
        == RiskLevel.MEDIUM
    )

    # 3. Base high risk
    assert SecurityPolicy.evaluate_risk("deploy", {}, base_risk=RiskLevel.HIGH) == RiskLevel.HIGH

    # 4. Target resource escalation: writing to /etc escalates to HIGH
    assert SecurityPolicy.evaluate_risk("write_file", {"path": "/etc/shadow"}) == RiskLevel.HIGH

    # 5. Dangerous shell commands escalate to HIGH
    assert SecurityPolicy.evaluate_risk("shell", {"cmd": "rm -rf /"}) == RiskLevel.HIGH
    assert SecurityPolicy.evaluate_risk("checkout", {"action": "payment_upi"}) == RiskLevel.HIGH

    assert SecurityPolicy.requires_human_approval(RiskLevel.HIGH) is True
    assert SecurityPolicy.requires_human_approval(RiskLevel.LOW) is False
