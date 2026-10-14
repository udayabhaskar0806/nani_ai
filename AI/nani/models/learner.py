"""N.A.N.I. V2 — Federated Multi-Model Learning Pipeline
Harvests bulk documentation via fast/free models (Groq Llama-3 / Ollama),
verifies actionable skills against machine grounding via reasoning models (Gemini / DeepSeek),
and persists learned knowledge into SQLite FTS5 for 2-5ms zero-token execution.
"""

import json
import re
import time
from typing import Any

from pydantic import BaseModel, Field

from nani.core.grounding import MachineGrounding
from nani.core.logger import logger as global_logger
from nani.memory.skills import SkillStore, VerifiedSkill
from nani.models.base import ModelCapability, ModelMessage, ModelRequest
from nani.models.router import ModelRouter
from nani.tools.document_reader import DocumentReader


class LearnedKnowledge(BaseModel):
    source: str
    title: str
    summary: str
    learned_skills: list[VerifiedSkill] = Field(default_factory=list)
    bulk_model_used: str = ""
    distillation_model_used: str = ""
    latency_ms: int = 0


class FederatedLearner:
    """Pipelines bulk document extraction and grounded skill learning across AI models."""

    def __init__(self, router: ModelRouter, skill_store: SkillStore) -> None:
        self.router = router
        self.skill_store = skill_store

    async def _summarize_chunk(self, chunk: str) -> str:
        """Uses fast/free model (Groq Llama-3 or Ollama) to compress text."""
        # Prefer groq or ollama for fast bulk processing
        provider = (
            self.router.get_provider("groq")
            or self.router.get_provider("ollama")
            or self.router.get_provider_for_capability(ModelCapability.FAST)
        )

        if not provider:
            return chunk[:1000]

        prompt = (
            "Summarize the technical facts, CLI tools, configuration files, and troubleshooting steps "
            f"from the following text into concise bullet points:\n\n{chunk}"
        )
        try:
            req = ModelRequest(
                capability=ModelCapability.FAST,
                messages=[ModelMessage(role="user", content=prompt)],
                temperature=0.1,
                max_tokens=1024,
            )
            resp = await provider.generate(req)
            return resp.content
        except Exception as exc:
            global_logger.log_event(
                event_type="LEARNER_CHUNK_FALLBACK",
                status="WARNING",
                data={"provider": provider.name, "error": str(exc)},
            )
            return chunk[:1000]

    async def _extract_actionable_skills(
        self, summary: str, source_title: str, grounding_snap: dict[str, Any]
    ) -> list[VerifiedSkill]:
        """Uses precision reasoning model (Gemini or DeepSeek) to turn summary into executable skills."""
        provider = (
            self.router.get_provider("gemini")
            or self.router.get_provider("deepseek")
            or self.router.get_provider_for_capability(ModelCapability.REASONING)
        )

        if not provider:
            return []

        installed_tools = ", ".join(grounding_snap.get("installed_tools", []))
        session_type = grounding_snap.get("session_type", "unknown")

        prompt = (
            f"You are the N.A.N.I. Skill Distiller. Source Document: '{source_title}'.\n"
            f"Digest:\n{summary}\n\n"
            f"Host Machine Facts:\n"
            f"- Installed tools: {installed_tools}\n"
            f"- Session: {session_type}\n\n"
            "Identify up to 3 concrete Linux commands or automated workflows mentioned that could be useful on this system.\n"
            "Output ONLY a valid JSON list of objects conforming to this schema:\n"
            "[\n"
            "  {\n"
            '    "intent_pattern": "regex pattern matching user requests, e.g. (check|read).*brightness",\n'
            '    "description": "Short description of what the skill does",\n'
            '    "required_tool": "name of binary needed (e.g. brightnessctl) or empty string",\n'
            '    "command_template": "exact shell command to execute",\n'
            '    "verification_rule": "how to verify output, e.g. exit_code == 0"\n'
            "  }\n"
            "]\n"
            "If no concrete executable actions exist, output []."
        )

        try:
            req = ModelRequest(
                capability=ModelCapability.REASONING,
                messages=[ModelMessage(role="user", content=prompt)],
                temperature=0.1,
                max_tokens=1500,
            )
            resp = await provider.generate(req)
            raw = resp.content.strip()

            # Clean JSON markdown blocks if present
            json_match = re.search(r"\[.*\]", raw, re.DOTALL)
            if json_match:
                raw = json_match.group(0)

            items = json.loads(raw)
            skills: list[VerifiedSkill] = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                cmd = item.get("command_template", "").strip()
                intent = item.get("intent_pattern", "").strip()
                if not cmd or not intent:
                    continue

                preconditions = {}
                req_tool = item.get("required_tool", "").strip()
                if req_tool:
                    preconditions["installed"] = [req_tool]

                skills.append(
                    VerifiedSkill(
                        intent_pattern=intent,
                        description=item.get("description", source_title),
                        preconditions=preconditions,
                        command_template=cmd,
                        verification_rule=item.get("verification_rule", "exit_code == 0"),
                    )
                )
            return skills

        except Exception as exc:
            global_logger.log_event(
                event_type="LEARNER_SKILL_EXTRACTION_ERROR",
                status="WARNING",
                data={"error": str(exc)},
            )
            return []

    async def learn_from_source(self, source: str, max_chars: int = 50_000) -> LearnedKnowledge:
        """Learns autonomously from a web URL, local document, or Linux man page."""
        t_start = time.monotonic()
        snap = MachineGrounding.get_snapshot()

        # Step 1: Ingest document
        if source.startswith("http://") or source.startswith("https://"):
            doc = await DocumentReader.read_url(source)
        elif source.startswith("man:"):
            doc = DocumentReader.read_man_page(source)
        else:
            doc = DocumentReader.read_local_file(source, max_chars=max_chars)

        content = doc["content"]
        title = doc["title"]

        # Step 2: Bulk processing via fast/free model chunks
        chunks = DocumentReader.chunk_content(content, chunk_size=3500, overlap=300)
        summaries: list[str] = []
        for ch in chunks[:5]:  # Process up to 5 chunks to bound runtime
            summ = await self._summarize_chunk(ch)
            summaries.append(summ)

        combined_summary = "\n\n".join(summaries)

        # Step 3: Grounded skill extraction via reasoning model
        skills = await self._extract_actionable_skills(combined_summary, title, snap)

        # Step 4: Persist knowledge and skills in SQLite
        self.skill_store.save_knowledge(
            source=source,
            title=title,
            content=content[:5000],
            summary=combined_summary[:2000],
            tags=["autonomous_learning", doc["source_type"]],
        )

        for sk in skills:
            self.skill_store.save_skill(sk)

        latency_ms = int((time.monotonic() - t_start) * 1000)

        global_logger.log_event(
            event_type="FEDERATED_LEARNING_COMPLETE",
            status="SUCCESS",
            data={
                "source": source,
                "title": title,
                "skills_extracted": len(skills),
                "latency_ms": latency_ms,
            },
        )

        return LearnedKnowledge(
            source=source,
            title=title,
            summary=combined_summary,
            learned_skills=skills,
            latency_ms=latency_ms,
        )
