"""Tests for N.A.N.I. V2 Sudo Privilege Management and Autonomous Sudo Execution."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from nani.core.grounding import MachineGrounding
from nani.core.sudo import SudoManager
from nani.tools.shell import ShellTool


@pytest.fixture(autouse=True)
def clean_sudo_state():
    """Ensure clean sudo state before and after each test."""
    SudoManager.clear()
    yield
    SudoManager.clear()


def test_sudo_manager_lifecycle():
    assert not SudoManager._session_password
    SudoManager.set_session_password("secret_pass")
    assert SudoManager.get_session_password() == "secret_pass"
    assert SudoManager.is_authorized() is True

    # Grounding prompt should reflect session credentials
    prompt = MachineGrounding.format_grounding_prompt()
    assert "Autonomous sudo authorized" in prompt

    SudoManager.clear()
    assert SudoManager.get_session_password() is None
    assert SudoManager._session_password is None


@pytest.mark.asyncio
async def test_sudo_manager_verify_invalid():
    # Empty password fails immediately
    assert await SudoManager.verify_password("") is False

    # Mock subprocess run returning failure
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 1
        ok = await SudoManager.verify_password("wrong_password")
        assert ok is False
        assert SudoManager.get_session_password() is None


@pytest.mark.asyncio
async def test_sudo_manager_authorize_success():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        ok = await SudoManager.authorize("valid_secret")
        assert ok is True
        assert SudoManager.get_session_password() == "valid_secret"
        assert SudoManager.is_authorized() is True


@pytest.mark.asyncio
async def test_shell_tool_injects_askpass_when_sudo_authorized(tmp_path: Path):
    SudoManager.set_session_password("test_pwd_123")
    tool = ShellTool(workspace_path=tmp_path, default_timeout=5.0)

    # Command without sudo runs without askpass
    with patch(
        "nani.tools.supervisor.SubprocessSupervisor.run_supervised", new_callable=AsyncMock
    ) as mock_super:
        mock_super.return_value.success = True
        mock_super.return_value.stdout = "hello"

        res = await tool.run(command="echo hello")
        assert res.success is True
        call_kwargs = mock_super.call_args.kwargs
        assert call_kwargs.get("env") is None
        assert call_kwargs.get("allow_unsandboxed") is False

    # Command with sudo should adapt to sudo -A and inject SUDO_ASKPASS
    with patch(
        "nani.tools.supervisor.SubprocessSupervisor.run_supervised", new_callable=AsyncMock
    ) as mock_super:
        mock_super.return_value.success = True
        mock_super.return_value.stdout = "root ok"

        res = await tool.run(command="sudo apt update")
        assert res.success is True
        call_kwargs = mock_super.call_args.kwargs
        assert call_kwargs.get("allow_unsandboxed") is True
        assert "env" in call_kwargs and call_kwargs["env"] is not None
        assert "SUDO_ASKPASS" in call_kwargs["env"]
        # Ensure command adapted to sudo -A
        argv = mock_super.call_args.kwargs.get("argv", [])
        assert any("sudo -A" in arg for arg in argv)


@pytest.mark.asyncio
async def test_sudo_manager_permanent_sudo_config():
    SudoManager.set_session_password("dummy")
    with patch("shutil.which", return_value="/usr/sbin/visudo"):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            success, msg = await SudoManager.configure_permanent_sudo("test_pwd")
            assert success is True
            assert "configured" in msg


@pytest.mark.asyncio
async def test_cli_authorize_sudo_flow(tmp_path: Path):
    from nani.core.orchestrator import Orchestrator
    from nani.core.task_manager import TaskManager
    from nani.interfaces.cli import InteractiveCLI
    from nani.memory.database import Database
    from nani.tools.registry import ToolRegistry

    db = Database(tmp_path / "test1.db")
    tm = TaskManager(db)
    reg = ToolRegistry()
    orch = Orchestrator(tm, reg)
    cli = InteractiveCLI(tm, reg, orch)

    with patch("getpass.getpass", return_value="my_pass"):
        with patch(
            "nani.core.sudo.SudoManager.verify_password", new_callable=AsyncMock
        ) as mock_ver:
            mock_ver.return_value = True
            ok = await cli.authorize_sudo()
            assert ok is True
            assert SudoManager.get_session_password() == "my_pass"

    # Revoke
    await cli.revoke_sudo()
    assert SudoManager.get_session_password() is None


@pytest.mark.asyncio
async def test_cli_natural_language_auth_trigger(tmp_path: Path):
    from nani.core.orchestrator import Orchestrator
    from nani.core.task_manager import TaskManager
    from nani.interfaces.cli import InteractiveCLI
    from nani.memory.database import Database
    from nani.tools.registry import ToolRegistry

    db = Database(tmp_path / "test2.db")
    tm = TaskManager(db)
    reg = ToolRegistry()
    orch = Orchestrator(tm, reg)
    cli = InteractiveCLI(tm, reg, orch)

    with patch.object(cli, "authorize_sudo", new_callable=AsyncMock) as mock_auth:
        mock_auth.return_value = True
        await cli.ask_model("i will give access to u")
        mock_auth.assert_called_once()
