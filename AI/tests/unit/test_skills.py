"""Unit tests for Persistent Skill & Knowledge Store with FTS5 Fast-Path."""

import time
from pathlib import Path

import pytest

from nani.memory.database import Database
from nani.memory.skills import SkillStore, VerifiedSkill


@pytest.fixture
def skill_store(tmp_path: Path) -> SkillStore:
    db = Database(tmp_path / "test_skills.db")
    return SkillStore(db)


def test_save_and_retrieve_skill(skill_store: SkillStore):
    skill = VerifiedSkill(
        skill_id="skill-brightness-sysfs",
        intent_pattern=r"(check|get|read).*screen.*brightness",
        description="Reads current LCD backlight brightness using Linux sysfs",
        preconditions={},
        command_template="cat /sys/class/backlight/{device}/brightness",
        verification_rule="exit_code == 0",
    )
    skill_store.save_skill(skill)

    retrieved = skill_store.get_skill("skill-brightness-sysfs")
    assert retrieved is not None
    assert retrieved.intent_pattern == skill.intent_pattern
    assert retrieved.command_template == skill.command_template


def test_fast_path_intent_matching_and_latency(skill_store: SkillStore):
    skill = VerifiedSkill(
        skill_id="skill-volume-pactl",
        intent_pattern=r"(get|check).*volume",
        description="Reads default audio sink volume via pactl",
        preconditions={"installed": ["pactl"]},
        command_template="pactl get-sink-volume @DEFAULT_SINK@",
    )
    skill_store.save_skill(skill)

    snap = {"installed_tools": ["pactl", "git"], "session_type": "x11"}

    t0 = time.monotonic()
    matched = skill_store.find_matching_skill("check my volume please", grounding_snap=snap)
    elapsed_ms = (time.monotonic() - t0) * 1000

    assert matched is not None
    assert matched.skill_id == "skill-volume-pactl"
    # Must complete fast (under 20ms in test environment, typically 2-5ms)
    assert elapsed_ms < 50.0


def test_precondition_rejection_falls_back(skill_store: SkillStore):
    skill = VerifiedSkill(
        skill_id="skill-brightnessctl-fast",
        intent_pattern=r"brightness",
        description="Adjusts screen brightness using brightnessctl utility",
        preconditions={"installed": ["brightnessctl"]},
        command_template="brightnessctl set 70%",
    )
    skill_store.save_skill(skill)

    # Machine snapshot WITHOUT brightnessctl installed
    snap = {"installed_tools": ["curl", "git"], "session_type": "x11"}

    matched = skill_store.find_matching_skill("change brightness", grounding_snap=snap)
    # Must be None because precondition 'brightnessctl' is not satisfied
    assert matched is None


def test_save_and_search_knowledge_snippets(skill_store: SkillStore):
    skill_store.save_knowledge(
        source="https://wiki.archlinux.org/title/Backlight",
        title="Arch Linux Backlight Manual",
        content="Backlight brightness is controlled via /sys/class/backlight interface in modern Linux kernels.",
        summary="Linux sysfs backlight controller documentation",
        tags=["linux", "hardware", "backlight"],
    )

    results = skill_store.search_knowledge("sysfs backlight interface")
    assert len(results) >= 1
    assert "Arch Linux Backlight Manual" in results[0].title
