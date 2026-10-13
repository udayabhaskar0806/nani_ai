"""N.A.N.I. V2 — Core Task & Plan State Contracts
Defines immutable data contracts for tasks, steps, actions, and observations.
"""

import time
import uuid
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    PAUSED = "PAUSED"
    CANCELLED = "CANCELLED"


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


class Action(BaseModel):
    action_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    step_id: str | None = None
    worker: str
    tool: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)
    duration_ms: int | None = None
    status: str = "PENDING"


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
    capability_required: str  # e.g. "coding", "browser", "computer", "system"
    status: StepStatus = StepStatus.PENDING
    risk_level: RiskLevel = RiskLevel.LOW
    actions: list[Action] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    error: str | None = None
    retry_count: int = 0
    max_retries: int = 3


class Task(BaseModel):
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    original_goal: str
    interpreted_goal: str | None = None
    workspace_path: str = "/home/dell/Vibe Coding"
    status: TaskStatus = TaskStatus.CREATED
    risk_level: RiskLevel = RiskLevel.LOW
    plan: list[PlanStep] = Field(default_factory=list)
    current_step_index: int = 0
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def mark_updated(self) -> None:
        self.updated_at = time.time()
