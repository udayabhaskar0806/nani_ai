"""Unit tests for Federated Multi-Model Learner."""

import json
from pathlib import Path

import pytest

from nani.memory.database import Database
from nani.memory.skills import SkillStore
from nani.models.base import ModelCapability, ModelProvider, ModelRequest, ModelResponse
from nani.models.learner import FederatedLearner
from nani.models.router import ModelRouter


class MockChunkProvider(ModelProvider):
    @property
    def name(self) -> str:
        return "groq"

    @property
    def supported_capabilities(self) -> list[ModelCapability]:
        return [ModelCapability.FAST]

    async def generate(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(
            content="- Learned fact 1: Screen brightness is controlled via /sys/class/backlight\n- Fact 2: pactl controls volume",
            provider_name=self.name,
            model_name="llama-3.3-70b",
        )

    async def is_available(self) -> bool:
        return True


class MockReasoningProvider(ModelProvider):
    @property
    def name(self) -> str:
        return "gemini"

    @property
    def supported_capabilities(self) -> list[ModelCapability]:
        return [ModelCapability.REASONING]

    async def generate(self, request: ModelRequest) -> ModelResponse:
        skills_json = json.dumps(
            [
                {
                    "intent_pattern": r"screen.*brightness",
                    "description": "Read screen brightness via kernel",
                    "required_tool": "",
                    "command_template": "cat /sys/class/backlight/intel_backlight/brightness",
                    "verification_rule": "exit_code == 0",
                }
            ]
        )
        return ModelResponse(
            content=f"```json\n{skills_json}\n```",
            provider_name=self.name,
            model_name="gemini-2.5-pro",
        )

    async def is_available(self) -> bool:
        return True


@pytest.mark.asyncio
async def test_federated_learner_pipeline(tmp_path: Path):
    # Setup test file to learn from
    doc_file = tmp_path / "linux_tips.md"
    doc_file.write_text("# Linux Control\nUse /sys/class/backlight to inspect screen brightness.")

    db = Database(tmp_path / "test_learn.db")
    skill_store = SkillStore(db)

    router = ModelRouter()
    router.register_provider(MockChunkProvider())
    router.register_provider(MockReasoningProvider())

    learner = FederatedLearner(router, skill_store)
    result = await learner.learn_from_source(str(doc_file))

    assert "linux_tips.md" in result.title
    assert len(result.learned_skills) == 1
    assert result.learned_skills[0].intent_pattern == r"screen.*brightness"

    # Verify skill was persisted in SQLite and can be found by SkillStore
    stored = skill_store.find_matching_skill("check screen brightness")
    assert stored is not None
    assert stored.command_template == "cat /sys/class/backlight/intel_backlight/brightness"

    # Verify knowledge snippet search works
    know = skill_store.search_knowledge("brightness")
    assert len(know) >= 1
