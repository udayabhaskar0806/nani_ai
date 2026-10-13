"""N.A.N.I. V2 — Standard Tool Execution Contract
Every native tool returns this standardized structure.
"""

from typing import Any

from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    success: bool
    data: dict[str, Any] = Field(default_factory=dict)
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    duration_ms: int = 0
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def ok(
        cls, data: dict[str, Any] | None = None, stdout: str = "", duration_ms: int = 0
    ) -> "ToolResult":
        return cls(
            success=True, data=data or {}, stdout=stdout, exit_code=0, duration_ms=duration_ms
        )

    @classmethod
    def fail(
        cls, error: str, stderr: str = "", exit_code: int = 1, duration_ms: int = 0
    ) -> "ToolResult":
        return cls(
            success=False, error=error, stderr=stderr, exit_code=exit_code, duration_ms=duration_ms
        )
