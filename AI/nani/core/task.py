"""N.A.N.I. V2 — Core Task & Plan State Contracts
Defines immutable data contracts for tasks, steps, actions, and observations.

TIMESTAMP STRATEGY:
All timestamps across N.A.N.I. core contracts (Task, Action, Observation, WorldState)
and SQLite database records use standard UTC epoch seconds as floating point numbers
(time.time()), ensuring microsecond precision, simple mathematical comparisons,
and effortless conversion to ISO 8601 UTC representation across all clients.
"""

import time
import uuid
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    RECOVERY = "RECOVERY"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    PAUSED = "PAUSED"
    CANCELLED = "CANCELLED"


class InvalidTaskTransition(ValueError):
    """Raised when an illegal task lifecycle transition is attempted."""

    pass


ALLOWED_TASK_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.CREATED: {TaskStatus.PLANNING, TaskStatus.CANCELLED},
    TaskStatus.PLANNING: {TaskStatus.RUNNING, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.RUNNING: {
        TaskStatus.VERIFYING,
        TaskStatus.WAITING,
        TaskStatus.RECOVERY,
        TaskStatus.PAUSED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.WAITING: {TaskStatus.RUNNING, TaskStatus.CANCELLED},
    TaskStatus.RECOVERY: {
        TaskStatus.RUNNING,
        TaskStatus.PLANNING,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.PAUSED: {TaskStatus.RUNNING, TaskStatus.CANCELLED},
    TaskStatus.VERIFYING: {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.COMPLETED: set(),
    TaskStatus.FAILED: set(),
    TaskStatus.CANCELLED: set(),
}


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class StepStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class ActionStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"


class WorkerCapability(str, Enum):
    """Answers: Which specialized N.A.N.I. worker can execute this plan step?

    Distinct from ModelCapability (which answers: What type of AI model is needed?).
    """

    CODING = "CODING"
    BROWSER = "BROWSER"
    COMPUTER = "COMPUTER"
    SYSTEM = "SYSTEM"
    RESEARCH = "RESEARCH"


class Action(BaseModel):
    action_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    step_id: str | None = None
    worker: str
    tool: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)
    duration_ms: int | None = None
    status: ActionStatus = ActionStatus.PENDING
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class Observation(BaseModel):
    observation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    action_id: str | None = None
    step_id: str | None = None
    timestamp: float = Field(default_factory=time.time)
    source: str  # "stdout", "stderr", "screen_ocr", "dom", "diff"
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class PlanStep(BaseModel):
    step_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    order: int
    description: str
    capability_required: WorkerCapability
    status: StepStatus = StepStatus.PENDING
    risk_level: RiskLevel = RiskLevel.LOW
    actions: list[Action] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    verification: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    retry_count: int = 0
    max_retries: int = 3


class Task(BaseModel):
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    original_goal: str
    interpreted_goal: str | None = None
    workspace_path: str = Field(default_factory=lambda: str(Path.cwd()))
    status: TaskStatus = TaskStatus.CREATED
    risk_level: RiskLevel = RiskLevel.LOW
    plan: list[PlanStep] = Field(default_factory=list)
    current_step_index: int = 0
    version: int = 1
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def mark_updated(self) -> None:
        self.updated_at = time.time()
