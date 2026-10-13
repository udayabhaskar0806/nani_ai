"""N.A.N.I. V2 — Structured Logging System
Provides JSONL and terminal logging with automatic redaction of sensitive credentials.
"""

import json
import re
import time
from pathlib import Path
from typing import Any

SENSITIVE_PATTERNS = [
    re.compile(
        r"(?i)(api[_-]?key|token|secret|password|bearer|auth|otp|cvv)\s*[:=]\s*['\"]?([^'\"\s,]+)"
    ),
    re.compile(r"AQ\.[a-zA-Z0-9_\-]{30,}"),  # Google AI Studio keys
    re.compile(r"gsk_[a-zA-Z0-9]{30,}"),  # Groq keys
]


def redact_sensitive_data(text: str) -> str:
    """Replaces sensitive tokens and keys with [REDACTED]."""
    redacted = text
    for pattern in SENSITIVE_PATTERNS:
        redacted = pattern.sub(r"\1: [REDACTED]", redacted)
    return redacted


class StructuredLogger:
    def __init__(self, log_dir: Path | None = None):
        self.log_dir = log_dir or Path("logs")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / "nani_events.jsonl"

    def log_event(
        self,
        event_type: str,
        task_id: str | None = None,
        step_id: str | None = None,
        worker: str | None = None,
        tool: str | None = None,
        status: str = "INFO",
        duration_ms: int | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        payload = {
            "timestamp": time.time(),
            "event_type": event_type,
            "task_id": task_id,
            "step_id": step_id,
            "worker": worker,
            "tool": tool,
            "status": status,
            "duration_ms": duration_ms,
            "data": data or {},
        }

        # Serialize and redact
        json_str = json.dumps(payload)
        safe_str = redact_sensitive_data(json_str)

        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(safe_str + "\n")
        except Exception:
            pass


logger = StructuredLogger()
