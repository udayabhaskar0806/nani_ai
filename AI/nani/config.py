"""N.A.N.I. V2 — Configuration Management
Loads environment variables and sets runtime paths, model capability routing defaults, and security rules.
"""

import os
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field


class Environment(str, Enum):
    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"


class Config(BaseModel):
    version: str = "2.0.0a1"
    env: Environment = Field(
        default_factory=lambda: Environment(os.getenv("NANI_ENV", "development"))
    )

    # Workspace & Paths
    workspace_root: Path = Field(
        default_factory=lambda: Path(
            os.getenv("NANI_WORKSPACE_ROOT", "/home/dell/Vibe Coding")
        ).resolve()
    )
    db_path: Path = Field(
        default_factory=lambda: Path(os.getenv("NANI_DB_PATH", "data/nani_v2.db"))
    )
    log_dir: Path = Field(default_factory=lambda: Path(os.getenv("NANI_LOG_DIR", "logs")))

    # Provider Keys (Loaded from .env)
    gemini_api_key: str | None = Field(default_factory=lambda: os.getenv("GEMINI_API_KEY"))
    groq_api_key: str | None = Field(default_factory=lambda: os.getenv("GROQ_API_KEY"))
    openrouter_api_key: str | None = Field(default_factory=lambda: os.getenv("OPENROUTER_API_KEY"))
    ollama_base_url: str = Field(
        default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    )

    # Safety Limits
    max_steps_per_task: int = Field(
        default_factory=lambda: int(os.getenv("NANI_MAX_STEPS_PER_TASK", "15"))
    )
    strict_safety_gate: bool = Field(
        default_factory=lambda: os.getenv("NANI_STRICT_SAFETY_GATE", "true").lower() == "true"
    )

    # Display Settings (Dell Latitude 3072x1728)
    display_normalized_coords: bool = True
    display_width: int = 3072
    display_height: int = 1728


# Singleton instance
settings = Config()
