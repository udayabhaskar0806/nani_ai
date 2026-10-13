"""N.A.N.I. Multi-AI Council (Consensus & Synthesis Engine)
Queries multiple distinct models in parallel, detects disagreements, filters hallucinations,
and synthesizes the single definitive Gold-Standard answer.
"""

import asyncio
from typing import List, Dict, Any, Optional
from nani.core.rotator import TokenRotator

class CouncilMember:
    def __init__(self, name: str, role: str, model: str, provider_name: str):
        self.name = name
        self.role = role
        self.model = model
        self.provider_name = provider_name

class MultiAICouncil:
    def __init__(self, rotator: Optional[TokenRotator] = None):
        self.rotator = rotator or TokenRotator()
        self.members = [
            CouncilMember("DeepSeek-R1", "Logic & Deep Chain-of-Thought", "deepseek/deepseek-r1:free", "openrouter"),
            CouncilMember("Llama 3.3 70B", "Broad Architecture & Systems", "llama-3.3-70b-versatile", "groq"),
            CouncilMember("Qwen 2.5 Coder", "Low-Level C/C++ & Algorithms", "qwen/qwen-2.5-coder-32b-instruct:free", "openrouter"),
            CouncilMember("Gemini Flash", "Fact-Checking & Large Context", "gemini-3.1-flash-lite", "gemini"),
        ]

    async def _query_member(self, member: CouncilMember, prompt: str) -> Dict[str, Any]:
        """Queries an individual council member asynchronously."""
        loop = asyncio.get_event_loop()
        system_role = (
            f"You are {member.name}, serving on an elite technical council. "
            f"Your specialty is {member.role}. Answer with high technical precision from first principles."
        )
        messages = [
            {"role": "system", "content": system_role},
            {"role": "user", "content": prompt}
        ]

        # Attempt query via rotator targeting specific model
        def _call():
            return self.rotator.chat_completion(messages, model_override=member.model)

        try:
            result = await loop.run_in_executor(None, _call)
            return {
                "member": member.name,
                "role": member.role,
                "success": result["success"],
                "content": result["content"] if result["success"] else f"Provider unavailable: {result.get('content')}"
            }
        except Exception as e:
            return {
                "member": member.name,
                "role": member.role,
                "success": False,
                "content": f"Execution error: {str(e)}"
            }

    async def convene(self, prompt: str) -> Dict[str, Any]:
        """Queries all council members in parallel and synthesizes the consensus."""
        # 1. Parallel dispatch
        tasks = [self._query_member(m, prompt) for m in self.members]
        responses = await asyncio.gather(*tasks, return_exceptions=False)

        # Filter successful responses
        valid_responses = [r for r in responses if r.get("success")]

        # If zero cloud providers succeeded (e.g. no keys set), fall back to primary rotator
        if not valid_responses:
            fallback = self.rotator.chat_completion([{"role": "user", "content": prompt}])
            synthesis = fallback.get("content", "All council members failed to respond.")
            return {
                "prompt": prompt,
                "responses": responses,
                "master_answer": synthesis,
                "discrepancies": "No external multi-model comparison possible without configured API keys. Response generated via local fallback."
            }

        # 2. Synthesis Pass: The Judge / Cross-Examiner
        synthesis_prompt = f"""You are N.A.N.I.'s Consensus Judge.
The user asked: "{prompt}"

Here are the independent deliberations from our Technical Council:
"""
        for r in valid_responses:
            synthesis_prompt += f"\n--- [{r['member']} - {r['role']}] ---\n{r['content'][:1500]}\n"

        synthesis_prompt += """
Your Task as the Chief Systems Architect:
1. THE GOLD-STANDARD MASTER ANSWER: Synthesize the absolute best, most accurate, and deeply technical solution. Strip away any hallucinations or vague generalities. Ground it in first-principles mechanics.
2. DISCREPANCY & CRITIQUE MATRIX: Point out where the models disagreed, what flaws one model caught that others missed, and why the consensus verdict is superior.
"""
        # Run synthesis through the primary active rotator provider
        synthesis_result = self.rotator.chat_completion([
            {"role": "system", "content": "You are N.A.N.I.'s Chief Consensus Judge. Synthesize council deliberations into one rigorous truth."},
            {"role": "user", "content": synthesis_prompt}
        ])

        master_text = synthesis_result.get("content", "Failed to generate synthesis.")

        return {
            "prompt": prompt,
            "responses": valid_responses,
            "master_answer": master_text,
            "models_consulted": [r["member"] for r in valid_responses]
        }
