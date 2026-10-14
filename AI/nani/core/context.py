"""N.A.N.I. V2 — Trusted Execution Context
Supplies immutable, runtime-verified execution parameters (task identity, workspace root, environment scope)
strictly separated from untrusted caller parameters.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

RESERVED_PARAMETER_KEYS = frozenset(
    {
        "workspace_path",
        "workspace",
        "context",
        "execution_context",
        "safe_cwd",
        "task_id",
        "step_id",
        "attempt_id",
    }
)


@dataclass(frozen=True)
class ExecutionContext:
    """Immutable execution context created solely by trusted orchestrator/task manager."""

    task_id: str
    workspace: Path
    step_id: str | None = None
    attempt_id: str = ""
    allowed_env: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "workspace", Path(self.workspace).resolve())

    def filter_untrusted_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """Rejects caller-supplied parameters attempting to override reserved context attributes."""
        clean = {}
        for k, v in params.items():
            if k in RESERVED_PARAMETER_KEYS:
                raise PermissionError(
                    f"Parameter injection rejected: reserved parameter '{k}' cannot be supplied by untrusted action caller."
                )
            clean[k] = v
        return clean
