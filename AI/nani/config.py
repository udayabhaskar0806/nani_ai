"""N.A.N.I. V2 — Hardened Configuration Management
Loads environment variables and .env using pydantic-settings with SecretStr masking.
Does not assume developer-specific workspace paths or physical screen resolutions.
"""

from enum import Enum
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    version: str = "2.0.0a1"
    env: Environment = Environment.DEVELOPMENT

    # Workspace & Dynamic Paths (Defaults to current working directory, not hardcoded machine path)
    workspace_root: Path = Field(default_factory=Path.cwd)
    db_path: Path = Path("data/nani_v2.db")
    log_dir: Path = Path("logs")

    # Model Provider Keys - SecretStr prevents accidental printing, repr, or logging
    gemini_api_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None
    openrouter_api_key: SecretStr | None = None
    ollama_base_url: str = "http://localhost:11434"

    # Safety Governance Limits
    max_steps_per_task: int = 15
    strict_safety_gate: bool = True

    def get_secret(self, key_name: str) -> str | None:
        """Retrieves unmasked secret value for authorized HTTP calls only."""
        secret_field = getattr(self, key_name, None)
        if isinstance(secret_field, SecretStr):
            return secret_field.get_secret_value()
        return None


# Singleton settings instance
settings = Config()
