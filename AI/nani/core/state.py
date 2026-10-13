"""N.A.N.I. V2 — World State Representation
Defines real-time telemetry, active window context, and repository states.
"""

from typing import Any

from pydantic import BaseModel, Field


class SystemState(BaseModel):
    cpu_model: str = "Unknown"
    cpu_percent: float = 0.0
    ram_available_mb: int = 0
    ram_total_mb: int = 0
    battery_percent: int | None = None
    on_ac: bool = True
    load_avg: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])


class DesktopState(BaseModel):
    active_window_title: str = ""
    active_window_wm_class: str = ""
    open_windows: list[str] = Field(default_factory=list)
    screen_resolution: str = "3072x1728"
    last_screenshot_path: str | None = None


class ProjectState(BaseModel):
    active_project_path: str | None = None
    build_system: str | None = None  # "make", "cmake", "cargo", "npm", "pytest"
    git_branch: str | None = None
    is_git_dirty: bool = False
    dirty_files: list[str] = Field(default_factory=list)


class WorldState(BaseModel):
    system: SystemState = Field(default_factory=SystemState)
    desktop: DesktopState = Field(default_factory=DesktopState)
    project: ProjectState = Field(default_factory=ProjectState)
    timestamp: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)
