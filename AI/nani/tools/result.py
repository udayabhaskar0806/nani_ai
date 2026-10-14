"""N.A.N.I. V2 — Standard Tool Execution Contract
Every native tool returns this standardized structure.
Process exit codes are optional and only populated when meaningful (e.g., shell/subprocess tools).
"""

from typing import Any

from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    success: bool
    data: dict[str, Any] = Field(default_factory=dict)
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = (
        None  # None for filesystem/API/GUI tools; int for shell/subprocess tools
    )
    duration_ms: int = 0
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def ok(
        cls,
        data: dict[str, Any] | None = None,
        stdout: str = "",
        stderr: str = "",
        exit_code: int | None = None,
        duration_ms: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> "ToolResult":
        return cls(
            success=True,
            data=data or {},
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            duration_ms=duration_ms,
            metadata=metadata or {},
        )

    @classmethod
    def fail(
        cls,
        error: str,
        stdout: str = "",
        stderr: str = "",
        exit_code: int | None = None,
        duration_ms: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> "ToolResult":
        return cls(
            success=False,
            error=error,
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            duration_ms=duration_ms,
            metadata=metadata or {},
        )
