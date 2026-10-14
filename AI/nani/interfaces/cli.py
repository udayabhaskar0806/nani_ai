"""N.A.N.I. V2 — Rich Interactive Terminal Interface (CLI)
Provides command prompt, live task tracking, hardware status bar, and autonomous agent loops.
"""

import asyncio
import re
import shutil
from pathlib import Path
from typing import Any

import httpx
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from nani.config import settings
from nani.core.context import ExecutionContext
from nani.core.grounding import MachineGrounding
from nani.core.intent import IntentClassifier, UserIntent
from nani.core.orchestrator import Orchestrator
from nani.core.sudo import SudoManager
from nani.core.task import TaskStatus
from nani.core.task_manager import TaskManager
from nani.memory.skills import SkillStore
from nani.models.base import ModelCapability
from nani.models.consensus import ConsensusEngine
from nani.models.learner import FederatedLearner
from nani.models.router import ModelRouter
from nani.tools.registry import ToolRegistry


class InteractiveCLI:
    """Rich interactive command line shell for N.A.N.I. V2."""

    def __init__(
        self,
        task_manager: TaskManager,
        registry: ToolRegistry,
        orchestrator: Orchestrator,
        model_router: ModelRouter | None = None,
    ) -> None:
        self.tm = task_manager
        self.registry = registry
        self.orchestrator = orchestrator
        self.model_router = model_router or ModelRouter.create_default()
        self.skill_store = SkillStore(self.tm.db)
        self.skill_store.seed_default_skills()
        self.consensus_engine = ConsensusEngine(self.model_router)
        self.learner = FederatedLearner(self.model_router, self.skill_store)
        self.intent_classifier = IntentClassifier(self.model_router, skill_store=self.skill_store)
        self.console = Console()
        self.history: list[dict[str, Any]] = []

    def print_banner(self) -> None:
        version = self.tm.db.get_schema_version()
        tools_count = len(self.registry.list_tools())
        self.console.print(
            Panel(
                f"[bold cyan]⚡ N . A . N . I .   V 2 ⚡[/bold cyan]\n"
                f"[italic bright_white]Neural Analytical Network Intelligence[/italic bright_white]\n"
                f"[dim cyan]v{settings.version} | Mode: {settings.env.value.upper()} | Schema: v{version} | Tools: {tools_count}[/dim cyan]",
                border_style="cyan",
            )
        )

    def display_status_table(self) -> None:
        table = Table(title="Runtime Subsystems Status", border_style="dim cyan")
        table.add_column("Subsystem", style="bold white")
        table.add_column("Status", style="green")
        table.add_column("Details", style="dim white")

        table.add_row("Database", "ONLINE", f"{settings.db_path} (WAL Mode)")
        table.add_row(
            "Tool Registry", "ONLINE", f"{len(self.registry.list_tools())} tools registered"
        )
        table.add_row("Action Journal", "ONLINE", "Durable sanitized SQLite journal")

        providers = self.model_router.list_providers()
        prov_names = [p.name for p in providers] or ["offline (none configured)"]
        table.add_row("Model Router", "ONLINE", f"Configured: {', '.join(prov_names)}")

        sudo_stat = "AUTONOMOUS ROOT" if SudoManager.is_authorized() else "STANDARD USER"
        sudo_stat_color = "bold green" if SudoManager.is_authorized() else "yellow"
        sudo_desc = (
            "Session password active"
            if SudoManager.get_session_password()
            else (
                "Passwordless sudo available"
                if MachineGrounding.check_sudo_privilege()
                else "Password required (run 'auth' to grant)"
            )
        )
        table.add_row("Privilege", f"[{sudo_stat_color}]{sudo_stat}[/{sudo_stat_color}]", sudo_desc)

        self.console.print(table)

    def _get_api_contents(self) -> list[dict[str, Any]]:
        """Returns bounded conversation history formatted for Gemini API."""
        if len(self.history) <= 30:
            return list(self.history)
        # Slice recent messages and ensure starting at valid user message
        sliced = self.history[-20:]
        while sliced:
            first = sliced[0]
            if first.get("role") == "user":
                parts = first.get("parts", [])
                if parts and "text" in parts[0]:
                    break
            sliced.pop(0)
        return sliced or list(self.history[-1:])

    async def execute_goal(self, goal: str) -> None:
        self.console.print(f"\n[bold green]▶ Initializing Task:[/bold green] [white]{goal}[/white]")
        task = self.tm.create_task(goal=goal)
        self.console.print(f"[dim]Task ID: {task.task_id} | Risk: {task.risk_level.value}[/dim]")

        with self.console.status("[bold cyan]Executing autonomous loop...[/bold cyan]"):
            final_task = await self.orchestrator.run_task(task.task_id)

        if final_task.status == TaskStatus.COMPLETED:
            self.console.print(
                f"[bold green]✓ Task Completed Successfully![/bold green] (Status: {final_task.status.value})\n"
            )
            detailed = self.tm.get_task(task.task_id)
            if detailed and detailed.plan:
                for step in detailed.plan:
                    for act in step.actions:
                        if act.result:
                            res_data = (
                                act.result.get("data")
                                if (isinstance(act.result, dict) and "data" in act.result)
                                else act.result
                            )
                            if isinstance(res_data, dict) and "results" in res_data:
                                for r in res_data["results"]:
                                    self.console.print(
                                        f"• [bold cyan]{r.get('title')}[/bold cyan]\n  [dim]{r.get('url')}[/dim]\n  {r.get('snippet')}\n"
                                    )
                            elif isinstance(res_data, dict) and res_data:
                                for k, v in res_data.items():
                                    self.console.print(f"  [cyan]{k}:[/cyan] {v}")
                                self.console.print()
                            elif act.result.get("stdout"):
                                stdout_text = str(act.result.get("stdout") or "").strip()
                                self.console.print(f"[dim]{stdout_text}[/dim]\n")
        elif final_task.status == TaskStatus.WAITING:
            self.console.print(
                f"[bold yellow]⏸ Task Paused — Approval Required[/bold yellow] (Status: {final_task.status.value})\n"
            )
        else:
            err = final_task.metadata.get("error", "Unknown error")
            if "UNSUPPORTED_GOAL" in str(err):
                # Conversational or unstructured prompt fallback to model
                self.console.print("[dim]Consulting AI model...[/dim]")
                await self.ask_model(goal)
                return
            self.console.print(
                f"[bold red]✗ Task Halted:[/bold red] {err} (Status: {final_task.status.value})\n"
            )

    def display_skills_table(self) -> None:
        """Displays stored verified skills and hit counts."""
        skills = self.skill_store.list_skills()
        if not skills:
            self.console.print(
                "[dim]No verified skills stored yet. Run 'learn: <url|file>' or ask tasks.[/dim]"
            )
            return

        table = Table(title="Verified Fast-Path Skills (2-5ms Execution)", border_style="dim cyan")
        table.add_column("Skill ID", style="dim white")
        table.add_column("Description", style="bold white")
        table.add_column("Command Template", style="cyan")
        table.add_column("Preconditions", style="yellow")
        table.add_column("Hits", style="green")

        for sk in skills:
            pre_str = ", ".join(f"{k}: {v}" for k, v in sk.preconditions.items()) or "None"
            table.add_row(
                sk.skill_id, sk.description, sk.command_template, pre_str, str(sk.success_count)
            )

        self.console.print(table)

    async def execute_council(self, question: str) -> None:
        """Runs multi-model deliberation and cross-critique rounds."""
        self.console.print(
            f"\n[bold magenta]🏛 Multi-Model Consensus Council Convening:[/bold magenta] [white]{question}[/white]"
        )
        try:
            with self.console.status(
                "[bold cyan]Arbitrating across AI models & cross-examining...[/bold cyan]"
            ):
                verdict = await self.consensus_engine.arbitrate(question)

            audit_text = "\n".join(f"• {a}" for a in verdict.audit_trail)
            self.console.print(
                Panel(
                    f"[bold green]Winner: {verdict.winner.provider_name} ({verdict.winner.model_name})[/bold green]\n"
                    f"Votes: {verdict.winning_votes}/{verdict.total_votes} | Confidence: {int(verdict.confidence * 100)}% | Machine Verified: {verdict.grounding_verified}\n\n"
                    f"[bold]Deliberation Audit Trail:[/bold]\n{audit_text}",
                    title="Council Deliberation Verdict",
                    border_style="magenta",
                )
            )

            if verdict.winner.extracted_command:
                cmd = verdict.winner.extracted_command
                self.console.print(
                    f"[dim]⚡ Running verified winning command: [cyan]{cmd}[/cyan]...[/dim]"
                )
                ctx = ExecutionContext(
                    task_id="cli_council",
                    workspace=Path.cwd().resolve(),
                    metadata={"allow_unsandboxed": True},
                )
                tool_res = await self.registry.execute("shell", {"command": cmd}, context=ctx)
                out = (tool_res.stdout or tool_res.stderr or "").strip()
                self.console.print(
                    f"\n[bold cyan]Result:[/bold cyan]\n{out or 'OK (exit code 0)'}\n"
                )
            else:
                self.console.print(
                    f"\n[bold cyan]NANI Council Response:[/bold cyan]\n{verdict.winner.content}\n"
                )
        except Exception as exc:
            self.console.print(f"[red]Council Deliberation Error: {exc}[/red]")

    async def execute_learning(self, source: str) -> None:
        """Autonomously ingests source and extracts skills."""
        self.console.print(
            f"\n[bold blue]📚 Federated Autonomous Learning from Source:[/bold blue] [white]{source}[/white]"
        )
        try:
            with self.console.status(
                "[bold cyan]Harvesting bulk data via Llama & distilling with Gemini...[/bold cyan]"
            ):
                learned = await self.learner.learn_from_source(source)

            self.console.print(
                Panel(
                    f"[bold green]Source Ingested:[/bold green] {learned.title} ({learned.latency_ms}ms)\n\n"
                    f"[bold cyan]Digest Summary:[/bold cyan]\n{learned.summary[:800]}...\n\n"
                    f"[bold magenta]Learned Actionable Skills:[/bold magenta] {len(learned.learned_skills)} stored into SQLite database.",
                    title="Learning Complete",
                    border_style="blue",
                )
            )
        except Exception as exc:
            self.console.print(f"[red]Learning Error: {exc}[/red]")

    def _build_tools_spec(self) -> list[dict[str, Any]]:
        """Returns Gemini function declaration schema for native system tools."""
        return [
            {
                "functionDeclarations": [
                    {
                        "name": "shell",
                        "description": (
                            "Executes a Linux bash command on the local machine (e.g. date, hostnamectl, "
                            "cat /sys/class/power_supply/BAT*/capacity, df -h, free -h, uptime, ps, ip a, git, etc.) "
                            "to inspect hardware, time, network, system info, launch applications, or run scripts."
                        ),
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "command": {
                                    "type": "STRING",
                                    "description": "The exact bash command to execute.",
                                }
                            },
                            "required": ["command"],
                        },
                    },
                    {
                        "name": "web_search",
                        "description": "Searches the web on DuckDuckGo when real-time external internet info, current news, or external documentation is required.",
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "query": {
                                    "type": "STRING",
                                    "description": "The search query.",
                                }
                            },
                            "required": ["query"],
                        },
                    },
                    {
                        "name": "read_file",
                        "description": "Reads the text content of a local file.",
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "path": {
                                    "type": "STRING",
                                    "description": "Relative or absolute path to the file.",
                                }
                            },
                            "required": ["path"],
                        },
                    },
                ]
            }
        ]

    async def authorize_sudo(self) -> bool:
        """Securely prompts for sudo credentials, verifies them, and registers them in volatile memory."""
        self.console.print("\n[bold cyan]🔐 Sudo Access Authorization[/bold cyan]")
        self.console.print(
            "[dim]Enter your Linux user password to authorize autonomous administrative tasks for NANI.\n"
            "Your password is held strictly in volatile RAM for this session and is never logged or saved to disk.[/dim]"
        )
        import getpass

        try:
            pwd = await asyncio.to_thread(getpass.getpass, "Password for sudo: ")
        except (KeyboardInterrupt, EOFError):
            self.console.print("\n[yellow]Authorization cancelled.[/yellow]\n")
            return False

        if not pwd:
            self.console.print("[yellow]Authorization cancelled (empty password).[/yellow]\n")
            return False

        with self.console.status("[bold cyan]Verifying sudo credentials...[/bold cyan]"):
            ok = await SudoManager.authorize(pwd)

        if ok:
            self.console.print(
                "[bold green]✓ Sudo access authorized successfully for this session![/bold green]\n"
                "[dim]NANI can now autonomously install software, update packages, and run administrative tasks.\n"
                "Tip: Run 'sudo permanent' if you want permanent passwordless execution without prompting next time.[/dim]\n"
            )
            return True
        else:
            self.console.print(
                "[bold red]✗ Sudo authentication failed: Incorrect password.[/bold red]\n"
            )
            return False

    async def setup_permanent_sudo(self) -> bool:
        """Configures /etc/sudoers.d/nani-sudo for permanent passwordless execution."""
        self.console.print("\n[bold cyan]⚙ Configuring Permanent Autonomous Sudo[/bold cyan]")
        if not SudoManager.is_authorized():
            self.console.print(
                "[yellow]Sudo credentials required to configure permanent access.[/yellow]"
            )
            ok = await self.authorize_sudo()
            if not ok:
                return False

        with self.console.status(
            "[bold cyan]Writing /etc/sudoers.d/nani-sudo (visudo syntax checked)...[/bold cyan]"
        ):
            success, msg = await SudoManager.configure_permanent_sudo()

        if success:
            self.console.print(f"[bold green]✓ {msg}[/bold green]\n")
            return True
        else:
            self.console.print(f"[bold red]✗ {msg}[/bold red]\n")
            return False

    async def revoke_sudo(self) -> None:
        """Revokes session and permanent sudo privileges."""
        SudoManager.clear()
        if MachineGrounding.check_sudo_privilege():
            with self.console.status(
                "[bold cyan]Removing permanent sudo configuration...[/bold cyan]"
            ):
                await SudoManager.remove_permanent_sudo()
        self.console.print(
            "[bold yellow]✓ Sudo authorization revoked. NANI is now running as standard user.[/bold yellow]\n"
        )

    async def ask_model(self, prompt: str) -> None:
        lower_prompt = prompt.strip().lower()

        # Natural language authorization intent check
        if any(
            phrase in lower_prompt
            for phrase in (
                "i will give access",
                "i'll give access",
                "give access",
                "grant access",
                "grant sudo",
                "authorize sudo",
                "give you access",
                "give u access",
                "grant root",
                "authorize root",
            )
        ) and not any(k in lower_prompt for k in ("how to", "why", "what is", "explain")):
            ok = await self.authorize_sudo()
            if ok:
                self.console.print(
                    "[bold cyan]NANI:[/bold cyan]\n"
                    "Thank you! Autonomous sudo access is active for this session. "
                    "What would you like me to install or configure for you? (e.g. 'install chrome')\n"
                )
            return

        # Step 1: Fast-Path Skill Check (2-5ms execution, zero tokens)
        snap = MachineGrounding.get_snapshot()
        matched_skill = self.skill_store.find_matching_skill(prompt, grounding_snap=snap)
        if matched_skill:
            self.console.print(
                f"[bold green]⚡ [Fast-Path 2ms Skill Hit]:[/bold green] [dim]{matched_skill.description}[/dim]"
            )
            cmd = matched_skill.command_template
            if "{device}" in cmd and snap.get("backlight"):
                cmd = cmd.replace("{device}", snap["backlight"]["device"])
            self.console.print(f"[dim]⚡ Running command: [cyan]{cmd}[/cyan]...[/dim]")
            ctx = ExecutionContext(
                task_id="cli_fast_skill",
                workspace=Path.cwd().resolve(),
                metadata={
                    "allow_unsandboxed": True,
                    "sudo_password": SudoManager.get_session_password(),
                },
            )
            tool_res = await self.registry.execute("shell", {"command": cmd}, context=ctx)
            out = (tool_res.stdout or tool_res.stderr or "").strip()
            self.console.print(
                f"\n[bold cyan]NANI (Zero-Token Fast Execution):[/bold cyan]\n{out or 'OK (exit code 0)'}\n"
            )
            return

        provider = self.model_router.get_provider_for_capability(ModelCapability.FAST)
        if not provider or not await provider.is_available():
            self.console.print(
                "[yellow]⚠ No active model provider configured. Set GEMINI_API_KEY or GROQ_API_KEY in .env.[/yellow]"
            )
            return

        api_key = getattr(provider, "api_key", None) or settings.get_secret("gemini_api_key")
        if not api_key:
            self.console.print("[yellow]⚠ Gemini API key is missing.[/yellow]")
            return

        # Step 2: Dynamic Semantic Intent Classification (SYSTEM vs LEARNING vs CONVERSATIONAL)
        intent_info = await self.intent_classifier.classify(prompt)
        intent = intent_info.intent

        if intent == UserIntent.LEARNING:
            snippets = self.skill_store.search_knowledge(prompt, limit=3)
            kb_context = ""
            if snippets:
                kb_context = (
                    "\nRelevant Digest Knowledge Base:\n"
                    + "\n".join(f"• {s.title}: {s.summary}" for s in snippets)
                    + "\n"
                )

            system_instruction = (
                "You are N.A.N.I., an autonomous AI engineer and personal assistant.\n"
                "The user is asking a conceptual, educational, or theoretical question.\n"
                f"{kb_context}\n"
                "Provide a clear, accurate, deep, and structured explanation in natural language.\n"
                "Include code snippets, architectural concepts, or real-world examples where helpful.\n"
                "DO NOT call shell tools or attempt to inspect host machine hardware for conceptual queries."
            )
            tools = None  # No shell tools for learning questions — prevents false executions!

        elif intent == UserIntent.SYSTEM:
            grounding_context = MachineGrounding.format_grounding_prompt()
            privilege_mode = (
                "AUTONOMOUS ROOT / SUDO ACTIVE: You are fully authorized to execute administrative and installation commands autonomously with sudo (e.g. sudo apt update && sudo apt install -y ..., sudo dpkg -i ..., sudo snap install ...)."
                if SudoManager.is_authorized()
                else "STANDARD USER: Sudo commands require password authorization. Do NOT guess passwords. Explain the command clearly for the user or prompt them: 'Type auth or grant access to let me install it autonomously.'"
            )
            system_instruction = (
                "You are N.A.N.I., an autonomous AI engineer and personal assistant running locally on the user's Linux machine.\n"
                "You have access to native tools: 'shell', 'web_search', and 'read_file'.\n"
                f"{grounding_context}\n"
                f"CURRENT PRIVILEGE STATUS: {privilege_mode}\n"
                "SYSTEM EXECUTION PRINCIPLES:\n"
                "1. VERIFY EXECUTABLES BEFORE CLAIMING SUCCESS:\n"
                "   - When asked to run or launch an application, verify its presence on $PATH before execution or reporting success.\n"
                "   - If an application is not installed, inform the user honestly, or proceed with autonomous installation if sudo is authorized.\n"
                "   - Launch GUI applications cleanly detached in the background.\n"
                "2. PRIVILEGE & SUDO REASONING:\n"
                "   - If autonomous root/sudo is active:\n"
                "     Execute the necessary package manager or installer commands autonomously (e.g. download deb package, sudo apt update, sudo apt install -y, or sudo snap install).\n"
                "     After installation, verify the binary is installed (e.g. 'which <bin>') before reporting completion.\n"
                "   - If standard user without sudo privilege is detected:\n"
                "     Do NOT run sudo commands in the background. Explain the commands or prompt the user: 'Run auth or grant access to let me install it for you.'\n"
                "   - Never attempt to guess, inject, or brute-force user passwords.\n"
                "3. INTEGRITY & NO SUBSTITUTION:\n"
                "   - Never launch, install, or substitute alternative applications without explicit user confirmation.\n"
                "4. HARDWARE & PROCESS INSPECTION:\n"
                "   - Use available tools to inspect system state factually and summarize the result clearly."
            )
            tools = self._build_tools_spec()

        else:
            system_instruction = (
                "You are N.A.N.I., a helpful, friendly, and knowledgeable AI assistant running locally on Linux.\n"
                "Answer conversationally and concisely."
            )
            tools = None

        # Add user prompt to multi-turn conversation history
        self.history.append({"role": "user", "parts": [{"text": prompt}]})
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent?key={api_key}"
        max_turns = 5

        async with httpx.AsyncClient(timeout=30.0) as client:
            for _ in range(max_turns):
                payload: dict[str, Any] = {
                    "systemInstruction": {"parts": [{"text": system_instruction}]},
                    "contents": self._get_api_contents(),
                }
                if tools:
                    payload["tools"] = tools

                resp = await client.post(url, json=payload)
                if resp.status_code != 200:
                    self.console.print(f"[red]Error from Gemini API: {resp.text[:300]}[/red]")
                    return

                res_json = resp.json()
                candidates = res_json.get("candidates", [])
                if not candidates:
                    self.console.print("[red]No candidate returned from AI model.[/red]")
                    return

                part = candidates[0].get("content", {}).get("parts", [{}])[0]

                if "functionCall" in part:
                    call = part["functionCall"]
                    fn_name = call.get("name")
                    fn_args = call.get("args", {})

                    if fn_name == "shell":
                        cmd = str(fn_args.get("command", "")).strip()

                        # Hard Security Guard: Automated password guessing / echo 'pwd' | sudo -S is prohibited
                        if re.search(r"echo\s+['\"].*?['\"]\s*\|\s*sudo\s+-S", cmd, re.IGNORECASE):
                            self.console.print(
                                "[bold red]🛑 Security Block: Automated password injection into sudo is forbidden.[/bold red]"
                            )
                            result_payload = {
                                "stdout": "",
                                "stderr": (
                                    "SECURITY ERROR: Automated password injection into sudo is forbidden. "
                                    "Do NOT attempt to guess passwords. Provide the command for the user to execute."
                                ),
                                "exit_code": 1,
                                "success": False,
                            }
                        # Launch Safety Guard: Prevent empty subshell nohup launches
                        elif cmd.startswith("nohup ") and "$(" in cmd and "which" in cmd:
                            m = re.search(r"which\s+([^)|>&]+)", cmd)
                            binaries = m.group(1).split() if m else []
                            found = any(shutil.which(b) for b in binaries)
                            if not found:
                                self.console.print(
                                    f"[yellow]⚠ Launch halted: Binary not found among [{', '.join(binaries)}].[/yellow]"
                                )
                                result_payload = {
                                    "stdout": "",
                                    "stderr": f"LAUNCH FAILED: None of ({', '.join(binaries)}) are installed on this system.",
                                    "exit_code": 127,
                                    "success": False,
                                }
                            else:
                                self.console.print(
                                    f"[dim]⚡ Running command: [cyan]{cmd}[/cyan]...[/dim]"
                                )
                                ctx = ExecutionContext(
                                    task_id="cli_interactive",
                                    workspace=Path.cwd().resolve(),
                                    metadata={
                                        "allow_unsandboxed": True,
                                        "sudo_password": SudoManager.get_session_password(),
                                    },
                                )
                                tool_res = await self.registry.execute(
                                    "shell", {"command": cmd}, context=ctx
                                )
                                out = (tool_res.stdout or tool_res.stderr or "").strip()
                                if not out:
                                    out = (
                                        "OK (exit code 0)"
                                        if tool_res.success
                                        else f"Command failed: {tool_res.error}"
                                    )
                                result_payload = {
                                    "stdout": out,
                                    "exit_code": tool_res.exit_code,
                                    "success": tool_res.success,
                                }
                        else:
                            self.console.print(
                                f"[dim]⚡ Running command: [cyan]{cmd}[/cyan]...[/dim]"
                            )
                            ctx = ExecutionContext(
                                task_id="cli_interactive",
                                workspace=Path.cwd().resolve(),
                                metadata={
                                    "allow_unsandboxed": True,
                                    "sudo_password": SudoManager.get_session_password(),
                                },
                            )
                            tool_res = await self.registry.execute(
                                "shell", {"command": cmd}, context=ctx
                            )
                            out = (tool_res.stdout or tool_res.stderr or "").strip()
                            if not out:
                                out = (
                                    "OK (exit code 0)"
                                    if tool_res.success
                                    else f"Command failed: {tool_res.error}"
                                )
                            result_payload = {
                                "stdout": out,
                                "exit_code": tool_res.exit_code,
                                "success": tool_res.success,
                            }
                    elif fn_name == "web_search":
                        query = str(fn_args.get("query", "")).strip()
                        self.console.print(f"[dim]🌐 Searching web: [cyan]{query}[/cyan]...[/dim]")
                        tool_res = await self.registry.execute(
                            "web_search", {"query": query, "max_results": 3}
                        )
                        result_payload = tool_res.data or {"results": []}
                    elif fn_name == "read_file":
                        path = str(fn_args.get("path", "")).strip()
                        self.console.print(f"[dim]📄 Reading file: [cyan]{path}[/cyan]...[/dim]")
                        tool_res = await self.registry.execute("read_file", {"path": path})
                        result_payload = {
                            "content": (
                                tool_res.data.get("content", "")
                                if tool_res.data
                                else tool_res.error
                            )
                        }
                    else:
                        result_payload = {"error": f"Tool '{fn_name}' not available"}

                    # Append model call and function response to history
                    self.history.append({"role": "model", "parts": [part]})
                    self.history.append(
                        {
                            "role": "user",
                            "parts": [
                                {
                                    "functionResponse": {
                                        "name": fn_name,
                                        "response": result_payload,
                                    }
                                }
                            ],
                        }
                    )
                else:
                    final_text = part.get("text", "")
                    self.history.append({"role": "model", "parts": [{"text": final_text}]})
                    self.console.print(f"\n[bold cyan]NANI:[/bold cyan]\n{final_text}\n")
                    return

            # Final summary if loop exhausted
            final_resp = await client.post(
                url,
                json={
                    "systemInstruction": {"parts": [{"text": system_instruction}]},
                    "contents": self._get_api_contents(),
                },
            )
            if final_resp.status_code == 200:
                p = (
                    final_resp.json()
                    .get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [{}])[0]
                )
                ans = p.get("text", "")
                if ans:
                    self.history.append({"role": "model", "parts": [{"text": ans}]})
                    self.console.print(f"\n[bold cyan]NANI:[/bold cyan]\n{ans}\n")

    async def run_loop(self) -> None:
        self.print_banner()
        self.display_status_table()
        self.console.print(
            "\nType your question, goal, or [bold cyan]'help'[/bold cyan] / [bold cyan]'exit'[/bold cyan].\n"
        )

        while True:
            try:
                line = input("nani ❯ ").strip()
                if not line:
                    continue
                if line.lower() in ("exit", "quit", "q"):
                    self.console.print("[dim]Shutting down NANI V2 runtime. Goodbye![/dim]")
                    break
                elif line.lower() == "help":
                    self.console.print(
                        "[bold]Commands & Capabilities:[/bold]\n"
                        "  status                 Show runtime subsystem status\n"
                        "  tools                  List all registered native tools\n"
                        "  skills                 List verified 2-5ms fast-path execution skills\n"
                        "  grounding / hardware   Show physical host machine factual ground truth\n"
                        "  clear                  Clear conversational memory\n"
                        "  council: <question>    Convene multi-model consensus council (debate & cross-examine)\n"
                        "  learn: <source>        Federated autonomous learning from URL, file, or man page\n"
                        "  auth / grant sudo      Authorize in-session sudo for autonomous root tasks\n"
                        "  sudo permanent         Configure permanent passwordless sudo (/etc/sudoers.d/nani-sudo)\n"
                        "  revoke                 Revoke sudo credentials\n"
                        "  <question>             Ask anything (fast-path skills auto-fire in 2ms)\n"
                        "  exit                   Exit NANI CLI\n"
                    )
                elif line.lower() == "status":
                    self.display_status_table()
                elif line.lower() in ("auth", "grant sudo", "sudo auth", "authorize sudo"):
                    await self.authorize_sudo()
                elif line.lower() in ("sudo permanent", "setup-sudo", "permanent sudo"):
                    await self.setup_permanent_sudo()
                elif line.lower() in ("revoke", "deauth", "revoke sudo"):
                    await self.revoke_sudo()
                elif line.lower() in ("grounding", "hardware"):
                    self.console.print(
                        Panel(
                            MachineGrounding.format_grounding_prompt(),
                            title="Host Machine Ground Truth",
                            border_style="cyan",
                        )
                    )
                elif line.lower() == "skills":
                    self.display_skills_table()
                elif line.lower() == "tools":
                    tools = self.registry.list_tools()
                    for name, t in sorted(tools.items()):
                        self.console.print(
                            f"  [cyan]{name:18}[/cyan] [dim]({t.capability.value:8})[/dim] {t.description}"
                        )
                elif line.lower() == "clear":
                    self.history.clear()
                    self.console.print("[dim]Conversational memory cleared.[/dim]")
                elif line.lower().startswith("council:") or line.lower().startswith("debate:"):
                    q = line.split(":", 1)[1].strip()
                    await self.execute_council(q)
                elif line.lower().startswith("learn:"):
                    src = line.split(":", 1)[1].strip()
                    await self.execute_learning(src)
                elif (
                    line.lower().startswith("task:")
                    or line.lower().startswith("goal:")
                    or line.lower().startswith("/task ")
                ):
                    goal_text = line.split(":", 1)[-1].strip() if ":" in line else line[6:].strip()
                    await self.execute_goal(goal_text)
                else:
                    # Autonomous AI reasoning with dynamic shell & web tool execution
                    await self.ask_model(line)
            except (KeyboardInterrupt, EOFError):
                self.console.print("\n[dim]Session terminated.[/dim]")
                break
            except Exception as e:
                self.console.print(f"[red]Error: {e}[/red]")


def run_cli() -> None:

    from nani.main import create_runtime

    tm, reg, orch = create_runtime()
    cli = InteractiveCLI(tm, reg, orch)
    asyncio.run(cli.run_loop())


if __name__ == "__main__":
    run_cli()
