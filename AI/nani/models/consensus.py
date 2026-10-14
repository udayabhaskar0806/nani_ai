"""N.A.N.I. V2 — Socratic Multi-Model Consensus & Arbitration Engine
Fans out queries across 4-5 models, detects disagreements, runs cross-examination rounds,
and tallies votes grounded in physical host machine state.
"""

import asyncio
import re
from typing import Any

from pydantic import BaseModel, Field

from nani.core.grounding import MachineGrounding
from nani.core.logger import logger as global_logger
from nani.models.base import ModelCapability, ModelMessage, ModelRequest
from nani.models.router import ModelRouter


class ModelCandidate(BaseModel):
    provider_name: str
    model_name: str
    content: str
    extracted_command: str | None = None
    latency_ms: int = 0
    round: int = 1
    conceded: bool = False
    conceded_to: str | None = None


class DebateRound(BaseModel):
    round_number: int
    proposals: list[ModelCandidate]
    disagreement_detected: bool = False
    critiques: dict[str, str] = Field(default_factory=dict)


class ConsensusVerdict(BaseModel):
    winner: ModelCandidate
    confidence: float
    consensus_reached: bool
    total_votes: int
    winning_votes: int
    rounds: list[DebateRound]
    audit_trail: list[str]
    grounding_verified: bool


class ConsensusEngine:
    """Orchestrates multi-model deliberation, cross-critique debate, and machine-grounded arbitration."""

    def __init__(
        self, router: ModelRouter, grounding: type[MachineGrounding] | None = None
    ) -> None:
        self.router = router
        self.grounding = grounding or MachineGrounding

    @staticmethod
    def extract_command(text: str) -> str | None:
        """Extracts bash/shell command from code block or direct command text."""
        # Check fenced code blocks ```bash ... ``` or ```sh ... ```
        block_match = re.search(
            r"```(?:bash|sh|shell)?\s*\n(.*?)\n```", text, re.DOTALL | re.IGNORECASE
        )
        if block_match:
            lines = [
                line.strip()
                for line in block_match.group(1).splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
            if lines:
                return lines[0]

        # Check inline backtick command `command`
        tick_match = re.search(r"`([^`]+)`", text)
        if tick_match:
            candidate = tick_match.group(1).strip()
            # Must look like a command (e.g. contains no spaces or starts with known cli token)
            if not candidate.startswith("http") and len(candidate) < 120:
                return candidate

        return None

    def _normalize_command_signature(self, cmd: str | None) -> str:
        """Extracts the root command token or normalized kernel path for clustering."""
        if not cmd:
            return ""
        cmd = cmd.strip()
        # If sysfs path
        if "/sys/class/backlight" in cmd or "/sys/class/power_supply" in cmd:
            return "sysfs_kernel_read"
        # First binary token
        tokens = cmd.split()
        if tokens:
            root = tokens[0].lower()
            if root in ("sudo", "cat", "echo") and len(tokens) > 1:
                return f"{root}_{tokens[1].lower()}"
            return root
        return ""

    def detect_disagreement(self, candidates: list[ModelCandidate]) -> bool:
        """Determines if models disagree on their proposed solutions or commands."""
        if len(candidates) <= 1:
            return False

        signatures = [
            self._normalize_command_signature(c.extracted_command)
            for c in candidates
            if c.extracted_command
        ]
        if len(signatures) > 1:
            # If commands exist and distinct signatures exist, disagreement is detected
            unique_sigs = set(signatures)
            if len(unique_sigs) > 1:
                return True

        # If no commands, compare word length or semantic keywords
        contents = [c.content.strip().lower() for c in candidates]
        if len(contents) > 1:
            # Check if one says yes and another says no
            has_yes = any("yes" in c[:50] or "true" in c[:50] for c in contents)
            has_no = any("no" in c[:50] or "false" in c[:50] for c in contents)
            if has_yes and has_no:
                return True

        return False

    async def _query_single_provider(
        self,
        provider_name: str,
        system_prompt: str,
        user_prompt: str,
        capability: ModelCapability,
    ) -> ModelCandidate | None:
        """Queries an individual model provider safely."""
        provider = self.router.get_provider(provider_name)
        if not provider:
            return None

        try:
            req = ModelRequest(
                capability=capability,
                messages=[ModelMessage(role="user", content=user_prompt)],
                system_prompt=system_prompt,
                temperature=0.2,
                max_tokens=1024,
            )
            resp = await provider.generate(req)
            cmd = self.extract_command(resp.content)
            return ModelCandidate(
                provider_name=resp.provider_name,
                model_name=resp.model_name,
                content=resp.content,
                extracted_command=cmd,
                latency_ms=resp.latency_ms,
            )
        except Exception as exc:
            global_logger.log_event(
                event_type="CONSENSUS_PROVIDER_SKIPPED",
                status="WARNING",
                data={"provider": provider_name, "error": str(exc)},
            )
            return None

    def _verify_against_machine(
        self, candidate: ModelCandidate, snap: dict[str, Any]
    ) -> tuple[bool, str]:
        """Validates candidate proposal against local host machine realities."""
        cmd = candidate.extracted_command
        if not cmd:
            return True, "No command to verify."

        installed_tools = set(snap.get("installed_tools", []))
        root_token = cmd.split()[0].lower() if cmd.split() else ""

        # If command uses a utility that is known NOT to be installed
        if root_token in MachineGrounding.KEY_BINARIES and root_token not in installed_tools:
            return False, f"Proposes tool '{root_token}' which is NOT installed on host system."

        # If xbacklight is used on Wayland or modern sysfs
        if "xbacklight" in cmd and snap.get("session_type") == "wayland":
            return False, "Proposes xbacklight on a Wayland session."

        return True, "Verified against machine grounding."

    async def arbitrate(
        self,
        question: str,
        capability: ModelCapability = ModelCapability.REASONING,
        providers: list[str] | None = None,
        max_rounds: int = 2,
    ) -> ConsensusVerdict:
        """Dispatches question across available models, moderates debates, and tallies consensus."""
        snap = self.grounding.get_snapshot()
        grounding_context = self.grounding.format_grounding_prompt()

        system_prompt = (
            "You are a sovereign Linux systems expert pair-programming in N.A.N.I. V2.\n"
            "Answer questions accurately based on the factual local machine ground truth provided.\n"
            "If a shell command or script is needed, output it inside a clean markdown code block.\n"
            f"\n{grounding_context}"
        )

        # Determine target providers
        candidate_provider_names = providers or [
            p.name for p in self.router.list_providers() if capability in p.supported_capabilities
        ]

        if not candidate_provider_names:
            raise RuntimeError(f"No configured providers support capability {capability.value}")

        rounds: list[DebateRound] = []
        audit_trail: list[str] = []

        # Round 1: Concurrent Fan-out
        audit_trail.append(
            f"Round 1: Fan-out to {len(candidate_provider_names)} models ({', '.join(candidate_provider_names)})"
        )
        tasks = [
            self._query_single_provider(name, system_prompt, question, capability)
            for name in candidate_provider_names
        ]
        results = await asyncio.gather(*tasks)
        r1_candidates = [r for r in results if r is not None]

        if not r1_candidates:
            raise RuntimeError(
                "All model providers failed to respond during consensus deliberation."
            )

        has_disagreement = self.detect_disagreement(r1_candidates)
        r1_round = DebateRound(
            round_number=1,
            proposals=r1_candidates,
            disagreement_detected=has_disagreement,
        )
        rounds.append(r1_round)

        active_candidates = r1_candidates

        # Round 2: Socratic Cross-Examination (only if disagreement and max_rounds >= 2)
        if has_disagreement and max_rounds >= 2 and len(r1_candidates) > 1:
            audit_trail.append(
                "Disagreement detected between models. Initiating Socratic Cross-Examination Round 2."
            )
            r2_candidates: list[ModelCandidate] = []

            for c in r1_candidates:
                rivals = [r for r in r1_candidates if r.provider_name != c.provider_name]
                rival_summaries = "\n".join(
                    f"- {r.provider_name} ({r.model_name}) proposed: {r.extracted_command or r.content[:150]}"
                    for r in rivals
                )

                cross_exam_prompt = (
                    f"Original Question: {question}\n\n"
                    f"Your Initial Proposal was:\n{c.content}\n\n"
                    f"Other models in council proposed different solutions:\n{rival_summaries}\n\n"
                    f"Local Machine Facts:\n{grounding_context}\n\n"
                    "Carefully examine the rival proposals against the local machine facts. "
                    "Are their proposals better or more compatible with this specific system? "
                    "If a rival proposal is superior, state clearly: 'I CONCEDE to [model/command]' and explain why. "
                    "If your original proposal is superior, defend it with technical facts."
                )

                critique_task = self._query_single_provider(
                    c.provider_name, system_prompt, cross_exam_prompt, capability
                )
                r2_resp = await critique_task
                if r2_resp:
                    r2_resp.round = 2
                    # Check for concession
                    resp_lower = r2_resp.content.lower()
                    if "i concede" in resp_lower or "conceding" in resp_lower:
                        r2_resp.conceded = True
                        for r in rivals:
                            if r.provider_name.lower() in resp_lower or (
                                r.extracted_command and r.extracted_command.lower() in resp_lower
                            ):
                                r2_resp.conceded_to = r.provider_name
                                break
                    r2_candidates.append(r2_resp)
                else:
                    r2_candidates.append(c)

            r2_round = DebateRound(
                round_number=2,
                proposals=r2_candidates,
                disagreement_detected=self.detect_disagreement(r2_candidates),
            )
            rounds.append(r2_round)
            active_candidates = r2_candidates

        # Tally Votes & Machine Verification
        vote_counts: dict[str, int] = {}
        for c in active_candidates:
            sig = self._normalize_command_signature(c.extracted_command) or c.provider_name
            if c.conceded and c.conceded_to:
                # Redirect vote to conceded recipient
                target = c.conceded_to
                vote_counts[target] = vote_counts.get(target, 0) + 1
                audit_trail.append(f"{c.provider_name} conceded to {c.conceded_to}.")
            else:
                vote_counts[sig] = vote_counts.get(sig, 0) + 1

        total_votes = len(active_candidates)

        # Sort candidate solutions by machine grounding compliance then vote count
        scored_candidates: list[tuple[float, ModelCandidate]] = []
        for c in active_candidates:
            if c.conceded:
                continue
            is_valid, reason = self._verify_against_machine(c, snap)
            sig = self._normalize_command_signature(c.extracted_command) or c.provider_name
            votes = vote_counts.get(sig, 1)

            # Grounding penalty / bonus
            score = float(votes)
            if not is_valid:
                score -= 10.0  # Disqualify physically broken commands
                audit_trail.append(f"Penalized {c.provider_name}: {reason}")
            else:
                score += 1.0  # Verified bonus

            scored_candidates.append((score, c))

        if not scored_candidates:
            # Fallback to first available candidate if all conceded
            winner = active_candidates[0]
            winning_votes = 1
        else:
            scored_candidates.sort(key=lambda x: x[0], reverse=True)
            winner = scored_candidates[0][1]
            winner_sig = (
                self._normalize_command_signature(winner.extracted_command) or winner.provider_name
            )
            winning_votes = vote_counts.get(winner_sig, 1)

        is_machine_verified, verify_reason = self._verify_against_machine(winner, snap)
        confidence = min(1.0, max(0.1, winning_votes / max(1, total_votes)))
        consensus_reached = winning_votes > (total_votes / 2)

        audit_trail.append(
            f"Verdict: Winner is {winner.provider_name} ({winner.model_name}) with {winning_votes}/{total_votes} votes. "
            f"Machine Verified: {is_machine_verified} ({verify_reason})"
        )

        global_logger.log_event(
            event_type="CONSENSUS_VERDICT",
            status="SUCCESS",
            data={
                "winner_provider": winner.provider_name,
                "winner_model": winner.model_name,
                "confidence": confidence,
                "consensus_reached": consensus_reached,
                "winning_votes": winning_votes,
                "total_votes": total_votes,
                "grounding_verified": is_machine_verified,
            },
        )

        return ConsensusVerdict(
            winner=winner,
            confidence=confidence,
            consensus_reached=consensus_reached,
            total_votes=total_votes,
            winning_votes=winning_votes,
            rounds=rounds,
            audit_trail=audit_trail,
            grounding_verified=is_machine_verified,
        )
