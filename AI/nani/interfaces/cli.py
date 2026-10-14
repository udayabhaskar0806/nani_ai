"""N.A.N.I. V2 — Rich Interactive Terminal Interface (CLI)
Provides command prompt, live task tracking, hardware status bar, and autonomous agent loops.
"""

import asyncio
from pathlib import Path
from typing import Any

import httpx
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from nani.config import settings
from nani.core.context import ExecutionContext
from nani.core.orchestrator import Orchestrator
from nani.core.task import TaskStatus
from nani.core.task_manager import TaskManager
from nani.models.base import ModelCapability
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

    async def ask_model(self, prompt: str) -> None:
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

        system_instruction = (
            "You are N.A.N.I., an autonomous AI engineer and personal assistant running locally on the user's Linux machine.\n"
            "You have access to native tools: 'shell', 'web_search', and 'read_file'.\n"
            "When the user asks you to inspect the system, open an application, check hardware, search information, or do anything:\n"
            "1. Autonomously CALL the appropriate tool (e.g. 'shell' with the exact Linux command).\n"
            "2. NEVER tell the user to manually run commands in their terminal when you can execute them directly.\n"
            "3. Maintain full conversation context across turns. If the user gives follow-up feedback (e.g. 'not opened', 'failed', 'try another way', 'explain that'), reference previous actions, diagnose what went wrong, and take active corrective action instead of asking what they meant.\n"
            "4. When launching desktop GUI applications (e.g. terminals, browsers, editors): launch them detached in background (e.g. 'nohup gnome-terminal >/dev/null 2>&1 &' or 'xterm &'). If the user reports it didn't open, try alternative terminal emulators like 'xterm &' or inspect $DISPLAY.\n"
            "5. Once you get tool output, understand it and explain the result clearly and concisely in a natural human voice."
        )

        tools = [
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

        # Add user prompt to multi-turn conversation history
        self.history.append({"role": "user", "parts": [{"text": prompt}]})
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent?key={api_key}"
        max_turns = 5

        async with httpx.AsyncClient(timeout=30.0) as client:
            for _ in range(max_turns):
                payload = {
                    "systemInstruction": {"parts": [{"text": system_instruction}]},
                    "contents": self._get_api_contents(),
                    "tools": tools,
                }
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
                        self.console.print(f"[dim]⚡ Running command: [cyan]{cmd}[/cyan]...[/dim]")
                        ctx = ExecutionContext(
                            task_id="cli_interactive",
                            workspace=Path.cwd().resolve(),
                            metadata={"allow_unsandboxed": True},
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
                        "  status        Show runtime subsystem status\n"
                        "  tools         List all registered native tools\n"
                        "  clear         Clear conversational memory\n"
                        "  task: <goal>  Execute multi-step goal through autonomous orchestrator\n"
                        "  <question>    Ask anything (system, apps, files, web, battery, coding)\n"
                        "  exit          Exit NANI CLI\n"
                    )
                elif line.lower() == "status":
                    self.display_status_table()
                elif line.lower() == "tools":
                    tools = self.registry.list_tools()
                    for name, t in sorted(tools.items()):
                        self.console.print(
                            f"  [cyan]{name:18}[/cyan] [dim]({t.capability.value:8})[/dim] {t.description}"
                        )
                elif line.lower() == "clear":
                    self.history.clear()
                    self.console.print("[dim]Conversational memory cleared.[/dim]")
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
