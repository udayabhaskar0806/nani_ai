"""N.A.N.I. V2 — Autonomous Research Worker Agent
Coordinates web search, webpage retrieval, and AI model synthesis.
Persists synthesized insights into NANI's episodic knowledge memory.
"""

import time
import uuid

from nani.agents.base import BaseWorker, WorkerResult
from nani.core.state import WorldState
from nani.core.task import Observation, PlanStep, WorkerCapability
from nani.memory.database import Database
from nani.models.base import ModelCapability, ModelMessage, ModelRequest
from nani.models.router import ModelRouter
from nani.tools.registry import ToolRegistry


class ResearchWorker(BaseWorker):
    """Autonomous research agent synthesizing online knowledge and updating persistent memory."""

    def __init__(
        self,
        tool_registry: ToolRegistry,
        model_router: ModelRouter | None = None,
        db: Database | None = None,
    ) -> None:
        self.tool_registry = tool_registry
        self.model_router = model_router or ModelRouter.create_default()
        self.db = db or Database()

    @property
    def capability_name(self) -> WorkerCapability:
        return WorkerCapability.RESEARCH

    async def can_handle(self, step: PlanStep, world_state: WorldState) -> bool:
        if step.capability_required == WorkerCapability.RESEARCH:
            return True
        desc = step.description.lower()
        return any(
            k in desc for k in ["search", "research", "find documentation", "lookup", "how to"]
        )

    async def execute(self, step: PlanStep, world_state: WorldState) -> WorkerResult:
        query = step.description
        if step.actions and "query" in step.actions[0].parameters:
            query = str(step.actions[0].parameters["query"])

        observations: list[Observation] = []

        # 1. Execute web search
        search_res = await self.tool_registry.execute(
            "web_search",
            {"query": query, "max_results": 3},
        )

        if not search_res.success:
            return WorkerResult.fail(
                error=f"Web search failed: {search_res.error}",
                summary=f"Research on '{query}' halted due to search failure.",
            )

        search_data = search_res.data or {}
        results = search_data.get("results", [])

        obs_search = Observation(
            source="web_search",
            content=f"Found {len(results)} search results for '{query}'.",
            metadata={"results_count": len(results)},
        )
        observations.append(obs_search)

        # 2. Fetch top webpage if available
        fetched_content = ""
        source_url = ""
        if results:
            top_url = results[0].get("url")
            if top_url:
                source_url = top_url
                fetch_res = await self.tool_registry.execute(
                    "fetch_web_page",
                    {"url": top_url, "max_length": 4000},
                )
                if fetch_res.success and fetch_res.data:
                    fetched_content = fetch_res.data.get("content", "")
                    obs_fetch = Observation(
                        source="fetch_web_page",
                        content=f"Fetched content from {top_url} ({len(fetched_content)} chars).",
                        metadata={"url": top_url, "title": fetch_res.data.get("title", "")},
                    )
                    observations.append(obs_fetch)

        # 3. Synthesize findings using Model Provider if configured, or deterministic fallback
        synthesized_text = ""
        provider = self.model_router.get_provider_for_capability(ModelCapability.RESEARCH)

        if provider and await provider.is_available():
            try:
                context_payload = f"Topic: {query}\n\nSearch Results:\n"
                for idx, r in enumerate(results, 1):
                    context_payload += (
                        f"[{idx}] {r.get('title')}: {r.get('snippet')} (URL: {r.get('url')})\n"
                    )

                if fetched_content:
                    context_payload += (
                        f"\nDetailed Content from {source_url}:\n{fetched_content[:3000]}\n"
                    )

                model_req = ModelRequest(
                    capability=ModelCapability.RESEARCH,
                    messages=[
                        ModelMessage(
                            role="user",
                            content=f"Synthesize a clear, accurate, and concise answer to the following topic based on these web sources:\n\n{context_payload}",
                        )
                    ],
                    system_prompt="You are N.A.N.I.'s Research Engine. Provide factual, concise technical syntheses with citations.",
                    max_tokens=1024,
                )
                model_resp = await provider.generate(model_req)
                synthesized_text = model_resp.content
            except Exception as e:
                # Graceful fallback to raw snippets if model call encounters network error
                synthesized_text = (
                    f"Synthesized research from {len(results)} sources (Model offline: {e}):\n"
                )
                for r in results:
                    synthesized_text += f"• {r.get('title')}: {r.get('snippet')}\n"
        else:
            # Deterministic offline synthesis
            synthesized_text = f"Research summary for '{query}':\n"
            for r in results:
                synthesized_text += f"- {r.get('title')}: {r.get('snippet')} ({r.get('url')})\n"

        # 4. Update NANI's persistent memory (episodic_memory table)
        now = time.time()
        episode_id = str(uuid.uuid4())
        try:
            with self.db.get_connection() as conn:
                conn.execute(
                    """INSERT INTO episodic_memory (episode_id, task_id, error_pattern, solution_summary, files_affected_json, timestamp)
                       VALUES (?, NULL, ?, ?, '[]', ?)""",
                    (episode_id, f"RESEARCH: {query}", synthesized_text, now),
                )
                conn.commit()
        except Exception:
            pass

        return WorkerResult.ok(
            summary=synthesized_text,
            observations=observations,
        )
