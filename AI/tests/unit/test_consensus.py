"""Unit tests for Socratic Multi-Model Consensus & Arbitration Engine."""

import pytest

from nani.models.base import ModelCapability, ModelProvider, ModelRequest, ModelResponse
from nani.models.consensus import (
    ConsensusEngine,
    ModelCandidate,
)
from nani.models.router import ModelRouter


class MockModelProvider(ModelProvider):
    def __init__(self, name: str, responses: list[str]) -> None:
        self._name = name
        self.responses = list(responses)
        self.call_count = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def supported_capabilities(self) -> list[ModelCapability]:
        return [ModelCapability.REASONING, ModelCapability.FAST]

    async def generate(self, request: ModelRequest) -> ModelResponse:
        content = self.responses[min(self.call_count, len(self.responses) - 1)]
        self.call_count += 1
        return ModelResponse(
            content=content,
            provider_name=self.name,
            model_name=f"{self.name}-v1",
            latency_ms=15,
        )

    async def is_available(self) -> bool:
        return True


def test_command_extraction_markdown_and_ticks():
    block = "To check brightness, run:\n```bash\ncat /sys/class/backlight/intel_backlight/brightness\n```"
    assert (
        ConsensusEngine.extract_command(block)
        == "cat /sys/class/backlight/intel_backlight/brightness"
    )

    inline = "You should use `brightnessctl get` to read it."
    assert ConsensusEngine.extract_command(inline) == "brightnessctl get"


def test_disagreement_detection():
    router = ModelRouter()
    engine = ConsensusEngine(router)

    c1 = ModelCandidate(
        provider_name="gemini",
        model_name="gemini-2.5",
        content="Use xbacklight",
        extracted_command="xbacklight -get",
    )
    c2 = ModelCandidate(
        provider_name="groq",
        model_name="llama-3",
        content="Use brightnessctl",
        extracted_command="brightnessctl get",
    )
    c3 = ModelCandidate(
        provider_name="ollama",
        model_name="qwen",
        content="Use brightnessctl",
        extracted_command="brightnessctl get",
    )

    assert engine.detect_disagreement([c1, c2, c3]) is True
    assert engine.detect_disagreement([c2, c3]) is False


@pytest.mark.asyncio
async def test_consensus_single_round_unanimous():
    router = ModelRouter()
    p1 = MockModelProvider(
        "gemini", ["Run ```bash\ncat /sys/class/backlight/device/brightness\n```"]
    )
    p2 = MockModelProvider("groq", ["Run ```bash\ncat /sys/class/backlight/device/brightness\n```"])
    router.register_provider(p1)
    router.register_provider(p2)

    engine = ConsensusEngine(router)
    verdict = await engine.arbitrate("How to read brightness?", max_rounds=1)

    assert verdict.consensus_reached is True
    assert verdict.total_votes == 2
    assert verdict.winning_votes == 2
    assert "cat /sys/class/backlight" in (verdict.winner.extracted_command or "")
    assert len(verdict.rounds) == 1


@pytest.mark.asyncio
async def test_consensus_multi_round_cross_examination_concession():
    router = ModelRouter()
    # Gemini starts with xbacklight, then concedes in Round 2
    p1 = MockModelProvider(
        "gemini",
        [
            "Run ```bash\nxbacklight -get\n```",
            "I concede to groq. xbacklight requires legacy X11 RANDR. cat /sys/class/backlight is better.",
        ],
    )
    # Groq defends sysfs
    p2 = MockModelProvider(
        "groq",
        [
            "Run ```bash\ncat /sys/class/backlight/intel/brightness\n```",
            "I defend my proposal: cat /sys/class/backlight is kernel-level and does not need external tools.",
        ],
    )

    router.register_provider(p1)
    router.register_provider(p2)

    engine = ConsensusEngine(router)
    verdict = await engine.arbitrate("Check brightness", max_rounds=2)

    assert len(verdict.rounds) == 2
    assert verdict.rounds[0].disagreement_detected is True
    assert verdict.winner.provider_name == "groq"
    assert any("conceded to groq" in a.lower() for a in verdict.audit_trail)


def test_machine_verification_penalizes_missing_binaries():
    router = ModelRouter()
    engine = ConsensusEngine(router)

    snap = {
        "installed_tools": ["git", "curl", "python3"],  # brightnessctl NOT installed
        "session_type": "x11",
    }

    bad_candidate = ModelCandidate(
        provider_name="model_a",
        model_name="a",
        content="use tool",
        extracted_command="brightnessctl set 50%",
    )
    good_candidate = ModelCandidate(
        provider_name="model_b",
        model_name="b",
        content="use sysfs",
        extracted_command="cat /sys/class/backlight/intel_backlight/brightness",
    )

    is_valid_bad, msg_bad = engine._verify_against_machine(bad_candidate, snap)
    is_valid_good, _ = engine._verify_against_machine(good_candidate, snap)

    assert is_valid_bad is False
    assert "NOT installed" in msg_bad
    assert is_valid_good is True
