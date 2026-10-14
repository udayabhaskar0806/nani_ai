"""N.A.N.I. V2 — Rich Interactive Terminal Interface (CLI)
Provides command prompt, live task tracking, hardware status bar, and autonomous agent loops.
"""

import asyncio

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from nani.config import settings
from nani.core.orchestrator import Orchestrator
from nani.core.task import TaskStatus
from nani.core.task_manager import TaskManager
from nani.models.base import ModelCapability, ModelMessage, ModelRequest
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

        self.console.print(f"[dim]Querying {provider.name}...[/dim]")
        req = ModelRequest(
            capability=ModelCapability.FAST,
            messages=[ModelMessage(role="user", content=prompt)],
            max_tokens=1024,
        )
        try:
            resp = await provider.generate(req)
            self.console.print(
                f"\n[bold cyan]NANI ({resp.provider_name} / {resp.model_name}):[/bold cyan]\n{resp.content}\n"
            )
        except Exception as e:
            self.console.print(f"[red]Error querying model: {e}[/red]")

    async def run_loop(self) -> None:
        self.print_banner()
        self.display_status_table()
        self.console.print(
            "\nType your goal, a command, or [bold cyan]'help'[/bold cyan] / [bold cyan]'exit'[/bold cyan].\n"
        )

        greetings = {
            "hi",
            "hello",
            "hey",
            "greetings",
            "who are you",
            "what can you do",
            "how are you",
            "good morning",
            "good afternoon",
            "good evening",
        }

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
                        "[bold]Commands:[/bold]\n"
                        "  status        Show runtime subsystem status\n"
                        "  tools         List all registered native tools\n"
                        "  ask <prompt>  Query configured AI model directly\n"
                        "  <goal>        Execute autonomous task loop for goal\n"
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
                elif line.lower() in greetings or line.endswith("?"):
                    await self.ask_model(line)
                elif line.lower().startswith("ask "):
                    prompt = line[4:].strip()
                    await self.ask_model(prompt)
                else:
                    await self.execute_goal(line)
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
