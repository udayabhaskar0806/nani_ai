"""N.A.N.I. V2 — Standard Worker Contract & Base Worker Interface
Defines the uniform execution contract for all specialized worker agents.
"""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from nani.core.state import WorldState
from nani.core.task import Observation, PlanStep, WorkerCapability


class WorkerResult(BaseModel):
    success: bool
    summary: str
    observations: list[Observation] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)
    next_recommendation: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def ok(
        cls,
        summary: str,
        observations: list[Observation] | None = None,
        changed_files: list[str] | None = None,
    ) -> "WorkerResult":
        return cls(
            success=True,
            summary=summary,
            observations=observations or [],
            changed_files=changed_files or [],
        )

    @classmethod
    def fail(cls, error: str, summary: str = "Execution failed") -> "WorkerResult":
        return cls(success=False, summary=summary, error=error)


class BaseWorker(ABC):
    @property
    @abstractmethod
    def capability_name(self) -> WorkerCapability:
        """WorkerCapability handled by this worker (e.g. WorkerCapability.CODING)."""
        pass

    @abstractmethod
    async def can_handle(self, step: PlanStep, world_state: WorldState) -> bool:
        """Evaluates whether this worker can execute the given plan step."""
        pass

    @abstractmethod
    async def execute(self, step: PlanStep, world_state: WorldState) -> WorkerResult:
        """Executes the step and returns structured worker outcome."""
        pass
