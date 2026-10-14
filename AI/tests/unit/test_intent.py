"""Unit tests for Semantic Intent Classifier."""

import pytest

from nani.core.intent import IntentClassifier, UserIntent
from nani.models.router import ModelRouter


@pytest.mark.asyncio
async def test_fallback_intent_without_model():
    classifier = IntentClassifier(router=None)

    # Conceptual should fallback to LEARNING
    res1 = await classifier.classify("what is an api")
    assert res1.intent == UserIntent.LEARNING

    # Explicit PC context should fallback to SYSTEM
    res2 = await classifier.classify("install chrome in this pc")
    assert res2.intent == UserIntent.SYSTEM

    # Empty string is CONVERSATIONAL
    res3 = await classifier.classify("   ")
    assert res3.intent == UserIntent.CONVERSATIONAL


@pytest.mark.asyncio
async def test_model_intent_classification():
    router = ModelRouter.create_default()
    classifier = IntentClassifier(router=router)

    # Test semantic differentiation between learning and system
    learning_res = await classifier.classify("what is an api")
    assert learning_res.intent == UserIntent.LEARNING

    system_res = await classifier.classify("open chrome")
    assert system_res.intent == UserIntent.SYSTEM
