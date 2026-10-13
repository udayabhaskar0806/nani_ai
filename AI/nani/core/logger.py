"""N.A.N.I. V2 — Structured Audit Logging System
Provides JSONL audit logging with comprehensive credential redaction and resilient failure handling.
Never crashes silently; exposes logging status and warns safely on stderr.
"""

import json
import re
import sys
import time
from pathlib import Path
from typing import Any

# Comprehensive credential redaction patterns supporting plain text and JSON-formatted text
SENSITIVE_PATTERNS = [
    # Key-value assignments: password=..., "token": "...", otp=..., cvv=842
    re.compile(
        r'(?i)("?\b(?:api[_-]?key|gemini[_-]?api[_-]?key|groq[_-]?api[_-]?key|secret|password|passwd|token|bearer|auth|otp|cvv)"?\s*[:=]\s*["\']?)([a-zA-Z0-9_\-\.]{3,})(["\']?)'
    ),
    # HTTP Authorization headers: Authorization: Bearer <token>
    re.compile(r"(?i)(Authorization:\s*Bearer\s+)[a-zA-Z0-9_\-\.]+"),
    # Well-known provider token prefixes
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),  # OpenAI
    re.compile(r"AIza[a-zA-Z0-9_\-]{30,}"),  # Google Cloud API key
    re.compile(r"AQ\.[a-zA-Z0-9_\-]{30,}"),  # Google Gemini AI Studio key
    re.compile(r"gsk_[a-zA-Z0-9]{30,}"),  # Groq Cloud key
]


def redact_sensitive_data(text: str) -> str:
    """Replaces sensitive tokens, keys, passwords, CVVs, and OTPs with [REDACTED]."""
    redacted = text
    for pattern in SENSITIVE_PATTERNS:
        if pattern.groups == 3:
            redacted = pattern.sub(r"\g<1>[REDACTED]\g<3>", redacted)
        elif pattern.groups == 1:
            redacted = pattern.sub(r"\1[REDACTED]", redacted)
        else:
            redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


class StructuredLogger:
    def __init__(self, log_dir: Path | None = None) -> None:
        self.log_dir = log_dir or Path("logs")
        self.log_file = self.log_dir / "nani_events.jsonl"
        self.has_logging_failures: bool = False
        self.last_logging_error: str | None = None
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self.has_logging_failures = True
            self.last_logging_error = f"Failed to create log directory: {e}"
            sys.stderr.write(f"[NANI Audit Logger Warning] {self.last_logging_error}\n")

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
    ) -> bool:
        """Logs a structured event to JSONL.

        Returns True on success, or False if file write failed (fallback warning emitted to stderr).
        """
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

        try:
            raw_json = json.dumps(payload)
            safe_entry = redact_sensitive_data(raw_json)
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(safe_entry + "\n")
            return True
        except Exception as e:
            self.has_logging_failures = True
            self.last_logging_error = f"Failed to write event {event_type}: {e}"
            # Safe stderr emission without printing data payload that might contain sensitive context
            sys.stderr.write(f"[NANI Audit Logger Error] {self.last_logging_error}\n")
            return False


# Global audit logger instance
logger = StructuredLogger()
