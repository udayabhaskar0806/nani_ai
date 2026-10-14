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

# Sensitive key names for structured dictionary redaction
SENSITIVE_KEY_NAMES = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "token",
        "api_key",
        "apikey",
        "gemini_api_key",
        "groq_api_key",
        "auth",
        "authorization",
        "credential",
        "private_key",
        "access_token",
        "bearer",
        "otp",
        "cvv",
    }
)

# Comprehensive credential redaction patterns supporting plain text, URLs, and JSON-formatted text
SENSITIVE_PATTERNS = [
    # Key-value assignments in JSON or plaintext: "password": "...", password=..., marker: ...
    re.compile(
        r'(?i)("?\b(?:api[_-]?key|gemini[_-]?api[_-]?key|groq[_-]?api[_-]?key|secret|password|passwd|token|bearer|auth|credential|otp|cvv)"?\s*[:=]\s*["\']?)([^"\'\s,}{\]]{3,})(["\']?)'
    ),
    # HTTP Authorization headers: Authorization: Bearer <token>
    re.compile(r"(?i)(Authorization:\s*Bearer\s+)[^\s,}{\]]+"),
    # Well-known provider token prefixes
    re.compile(r"sk-[a-zA-Z0-9_\-]{20,}"),  # OpenAI
    re.compile(r"AIza[a-zA-Z0-9_\-]{30,}"),  # Google Cloud API key
    re.compile(r"AQ\.[a-zA-Z0-9_\-]{30,}"),  # Google Gemini AI Studio key
    re.compile(r"gsk_[a-zA-Z0-9_\-]{30,}"),  # Groq Cloud key
]


def redact_sensitive_data(text: str) -> str:
    """Replaces sensitive tokens, keys, passwords, CVVs, and OTPs with [REDACTED]."""
    if not isinstance(text, str):
        text = str(text)
    redacted = text
    for pattern in SENSITIVE_PATTERNS:
        if pattern.groups == 3:
            redacted = pattern.sub(r"\g<1>[REDACTED]\g<3>", redacted)
        elif pattern.groups == 1:
            redacted = pattern.sub(r"\1[REDACTED]", redacted)
        else:
            redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def sanitize_data_structure(data: Any) -> Any:
    """Recursively traverses dictionaries and lists to redact sensitive keys and values."""
    if data is None:
        return None
    if isinstance(data, dict):
        sanitized: dict[str, Any] = {}
        for k, v in data.items():
            k_lower = str(k).lower().replace("-", "_")
            if any(s in k_lower for s in SENSITIVE_KEY_NAMES):
                sanitized[k] = "[REDACTED]"
            else:
                sanitized[k] = sanitize_data_structure(v)
        return sanitized
    elif isinstance(data, (list, tuple)):
        return [sanitize_data_structure(item) for item in data]
    elif isinstance(data, str):
        return redact_sensitive_data(data)
    else:
        return data


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
        """Logs a structured event to JSONL with complete credential sanitization."""
        safe_data = sanitize_data_structure(data or {})
        payload = {
            "timestamp": time.time(),
            "event_type": event_type,
            "task_id": task_id,
            "step_id": step_id,
            "worker": worker,
            "tool": tool,
            "status": status,
            "duration_ms": duration_ms,
            "data": safe_data,
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
            sys.stderr.write(f"[NANI Audit Logger Error] {self.last_logging_error}\n")
            return False


# Global audit logger instance
logger = StructuredLogger()
