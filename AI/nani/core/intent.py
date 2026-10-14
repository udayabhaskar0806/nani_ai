"""N.A.N.I. V2 — Semantic Intent Classifier
Distinguishes dynamically between SYSTEM actions (local host operations, hardware, apps)
and LEARNING/KNOWLEDGE queries (conceptual questions, explanations, theory)
using fast model inference without fragile hardcoded prefix lists.
"""

import json
import logging
import re
from enum import Enum

from pydantic import BaseModel

from nani.models.base import ModelCapability, ModelMessage, ModelRequest
from nani.models.router import ModelRouter

logger = logging.getLogger(__name__)


class UserIntent(str, Enum):
    SYSTEM = "SYSTEM"  # Operating system tasks, hardware, processes, packages, files, local actions
    LEARNING = (
        "LEARNING"  # Conceptual questions, technical explanations, definitions, theory, tutorials
    )
    CONVERSATIONAL = "CONVERSATIONAL"  # Greetings, identity, meta-questions


class IntentClassification(BaseModel):
    intent: UserIntent
    confidence: float = 1.0
    rationale: str = ""


class IntentClassifier:
    """Classifies user prompts into SYSTEM, LEARNING, or CONVERSATIONAL intents."""

    CLASSIFICATION_PROMPT = (
        "You are an intent classifier for N.A.N.I., an autonomous AI assistant on a Linux system.\n"
        "Classify the user input into exactly one category:\n"
        "- SYSTEM: Actions, inspections, hardware, processes, files, package management, application launching, or terminal operations on this local computer.\n"
        "- LEARNING: Conceptual questions, technical explanations, definitions, theory, tutorials, coding questions, or computer science knowledge.\n"
        "- CONVERSATIONAL: Greetings, identity, meta-questions.\n"
        'Output ONLY a JSON object: {"intent": "SYSTEM" | "LEARNING" | "CONVERSATIONAL", "rationale": "brief reason"}'
    )

    def __init__(self, router: ModelRouter | None = None) -> None:
        self.router = router

    async def classify(self, query: str) -> IntentClassification:
        clean_q = query.strip()
        if not clean_q:
            return IntentClassification(intent=UserIntent.CONVERSATIONAL, rationale="Empty query")

        # 1. Use fast model (Groq, Ollama, Gemini) if available
        if self.router:
            provider = (
                self.router.get_provider("groq")
                or self.router.get_provider("ollama")
                or self.router.get_provider_for_capability(ModelCapability.FAST)
            )
            if provider and await provider.is_available():
                try:
                    req = ModelRequest(
                        capability=ModelCapability.FAST,
                        messages=[
                            ModelMessage(role="system", content=self.CLASSIFICATION_PROMPT),
                            ModelMessage(role="user", content=clean_q),
                        ],
                        temperature=0.0,
                        max_tokens=50,
                    )
                    res = await provider.generate(req)
                    # Extract JSON object from output
                    match = re.search(r"\{.*?\}", res.content, re.DOTALL)
                    if match:
                        data = json.loads(match.group(0))
                        intent_str = str(data.get("intent", "")).upper()
                        if intent_str in UserIntent.__members__:
                            return IntentClassification(
                                intent=UserIntent(intent_str),
                                rationale=str(data.get("rationale", "")),
                            )
                except Exception as exc:
                    logger.debug("Fast model intent classification failed, using fallback: %s", exc)

        # 2. Resilient fallback when no AI model is reachable
        lower = clean_q.lower()
        if any(
            w in lower
            for w in (
                "this pc",
                "this computer",
                "my laptop",
                "my system",
                "sudo ",
                "apt ",
                "dpkg ",
                "chmod ",
                "kill ",
                "systemctl ",
            )
        ):
            return IntentClassification(
                intent=UserIntent.SYSTEM, rationale="Local PC direct context"
            )

        # Default to LEARNING for general questions / concepts
        return IntentClassification(
            intent=UserIntent.LEARNING, rationale="Fallback knowledge route"
        )
