"""Unit tests for structured audit logger, credential redaction, and resilient failure handling."""

import sys
from io import StringIO
from pathlib import Path

import pytest

from nani.core.logger import StructuredLogger, redact_sensitive_data


def test_secret_redaction_patterns():
    secret_payloads = [
        (
            "GEMINI_API_KEY=AQ.Ab8RN6Jm6BroZJMXlgTwuEZKtOXd_8wm",
            "AQ.Ab8RN6Jm6BroZJMXlgTwuEZKtOXd_8wm",
            "GEMINI_API_KEY=[REDACTED]",
        ),
        (
            "GROQ_API_KEY=gsk_1234567890abcdef1234567890abcdef",
            "gsk_1234567890abcdef1234567890abcdef",
            "GROQ_API_KEY=[REDACTED]",
        ),
        (
            "Authorization: Bearer my_secret_bearer_token_xyz",
            "my_secret_bearer_token_xyz",
            "Authorization: Bearer [REDACTED]",
        ),
        ("password=supersecretpassword123", "supersecretpassword123", "password=[REDACTED]"),
        (
            "token=ghp_abcdefghijklmnopqrstuvwxyz123456",
            "ghp_abcdefghijklmnopqrstuvwxyz123456",
            "token=[REDACTED]",
        ),
        ("otp=984512", "984512", "otp=[REDACTED]"),
        ("cvv=842", "842", "cvv=[REDACTED]"),
        (
            "Using key sk-abcdefghijklmnopqrstuvwxyz123456 for auth",
            "sk-abcdefghijklmnopqrstuvwxyz123456",
            "Using key [REDACTED] for auth",
        ),
        (
            "Using Google key AIzaSyA1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6 for vision",
            "AIzaSyA1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6",
            "Using Google key [REDACTED] for vision",
        ),
    ]

    for raw, secret, expected in secret_payloads:
        redacted = redact_sensitive_data(raw)
        assert redacted == expected
        # Ensure the secret itself is NEVER present in the output
        assert secret not in redacted
        assert "[REDACTED]" in redacted


def test_logger_file_output(tmp_path: Path):
    log_dir = tmp_path / "audit_logs"
    s_logger = StructuredLogger(log_dir)

    success = s_logger.log_event(
        event_type="TOOL_EXECUTION",
        task_id="task-001",
        tool="read_file",
        data={"path": "main.c", "token": "sensitive_token_999"},
    )

    assert success is True
    assert s_logger.has_logging_failures is False

    log_content = (log_dir / "nani_events.jsonl").read_text()
    assert "TOOL_EXECUTION" in log_content
    assert "task-001" in log_content
    assert "sensitive_token_999" not in log_content
    assert "[REDACTED]" in log_content


def test_logger_failure_handling_emits_stderr_safely(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    # Point logger to a path that cannot be written (directory acting as file)
    bad_log_dir = tmp_path / "bad_dir"
    bad_log_dir.mkdir()
    # Create a directory with the same name as the target log file to force an IOError
    (bad_log_dir / "nani_events.jsonl").mkdir()

    stderr_capture = StringIO()
    monkeypatch.setattr(sys, "stderr", stderr_capture)

    s_logger = StructuredLogger(bad_log_dir)
    success = s_logger.log_event(event_type="TEST_EVENT", task_id="task-err")

    # Logger must not raise an unhandled exception; it returns False and records failure state
    assert success is False
    assert s_logger.has_logging_failures is True
    assert s_logger.last_logging_error is not None

    # Stderr should contain safe warning without crashing
    stderr_output = stderr_capture.getvalue()
    assert "[NANI Audit Logger Error]" in stderr_output
