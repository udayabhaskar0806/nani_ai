"""N.A.N.I. Interactive Terminal Console
A cyberpunk / Stark-inspired CLI interface powered by Rich.
"""

import sys
import asyncio
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown
from rich.text import Text
from rich.live import Live

from nani.config import Config
from nani.core.memory import MemoryStore
from nani.core.engine import LLMEngine
from nani.core.council import MultiAICouncil
from nani.tools.github_radar import GitHubRadar
from nani.tools.researcher import DeepResearcher
from nani.tools.reminders import ReminderManager
from nani.tools.system_ops import SystemOps
from nani.tools.laptop_control import LaptopController
from nani.core.agent import SystemAgent

console = Console()

class NaniCLI:
    def __init__(self):
        self.memory = MemoryStore()
        self.engine = LLMEngine(memory=self.memory)
        self.council = MultiAICouncil(rotator=self.engine.rotator)
        self.agent = SystemAgent(memory=self.memory, engine=self.engine)
        self.radar = GitHubRadar()
        self.researcher = DeepResearcher()
        self.reminders = ReminderManager(memory=self.memory)
        self.laptop = LaptopController()

    def print_banner(self):
        banner_text = Text()
        banner_text.append("⚡ N . A . N . I . ⚡\n", style="bold cyan")
        banner_text.append("Neural Analytical Network Intelligence\n", style="italic bright_white")
        banner_text.append(f"v{Config.VERSION} | Core Systems Co-Pilot | First-Principles Engine", style="dim cyan")
        
        console.print(Panel(banner_text, border_style="cyan", padding=(1, 2)))

    def show_stats(self):
        stats = SystemOps.get_hardware_telemetry()
        table = Table(title="🖥️ Linux Hardware & Core Telemetry", border_style="bright_blue")
        table.add_column("Metric", style="cyan", justify="left")
        table.add_column("Value", style="bold white", justify="left")

        table.add_row("CPU Architecture", f"{stats['cpu_model']} ({stats['arch']})")
        table.add_row("Linux Kernel", stats["kernel"])
        table.add_row("RAM Utilization", f"{stats['ram_available_mb']} MB available / {stats['ram_total_mb']} MB ({stats['ram_percent_used']}% used)")
        table.add_row("System Load (1, 5, 15m)", str(stats["load_avg"]))
        table.add_row("Database Memory", f"SQLite @ {Config.DB_PATH}")

        console.print(table)

    def handle_radar(self, arg: str):
        query = arg if arg else "topic:llm OR topic:inference OR topic:deep-learning"
        console.print(f"\n[cyan]🛰️ Scanning GitHub AI Radar with query: '[bold white]{query}[/bold white]'...[/cyan]")
        
        repos = self.radar.scan_trending_ai(query=query, limit=6)
        if not repos or "error" in repos[0]:
            err_msg = repos[0].get("error") if repos else "No repositories returned."
            console.print(f"[red]Failed to scan GitHub: {err_msg}[/red]")
            return

        table = Table(title="🚀 GitHub AI Radar: Fast-Moving Repositories", border_style="cyan")
        table.add_column("Repository", style="bold bright_yellow")
        table.add_column("Lang", style="green")
        table.add_column("Stars", style="magenta", justify="right")
        table.add_column("Description", style="white")

        for r in repos:
            table.add_row(
                r["name"],
                r["language"],
                str(r["stars"]),
                r["description"][:70] + "..." if len(r["description"]) > 70 else r["description"]
            )
        console.print(table)
        console.print("[dim cyan]Tip: Type '/inspect <owner/repo>' to run a deep architectural breakdown of any repo![/dim cyan]\n")

    def handle_inspect(self, repo_name: str):
        if not repo_name:
            console.print("[red]Usage: /inspect <owner/repo>[/red]")
            return

        console.print(f"\n[cyan]🔍 Fetching README & file tree for [bold white]{repo_name}[/bold white]...[/cyan]")
        with console.status("[cyan]N.A.N.I. is dissecting repository architecture...[/cyan]"):
            analysis = self.radar.analyze_repo(repo_name, self.engine)

        console.print(Panel(Markdown(analysis), title=f"⚡ Architecture Breakdown: {repo_name}", border_style="bright_blue"))

    def handle_research(self, topic: str):
        if not topic:
            console.print("[red]Usage: /research <topic or question>[/red]")
            return

        console.print(f"\n[cyan]🔬 Commencing Deep First-Principles Research into: '[bold white]{topic}[/bold white]'...[/cyan]")
        with console.status("[cyan]Querying web sources & running recursive 'Why?' analysis...[/cyan]"):
            report = self.researcher.research(topic, self.engine)

        console.print(Panel(Markdown(report), title=f"🧠 Deep Research Dossier: {topic}", border_style="magenta"))

    def handle_remind(self, arg: str):
        parts = arg.split(maxsplit=1)
        if len(parts) < 2 or not parts[0].isdigit():
            console.print("[red]Usage: /remind <minutes> <task description>[/red]")
            console.print("[dim]Example: /remind 15 Check on model training process[/dim]")
            return

        mins = int(parts[0])
        task = parts[1]
        job = self.reminders.schedule_in_minutes(task, mins)
        console.print(f"[green]✓ Reminder registered: '[bold white]{job['task']}[/bold white]' in {mins} minutes (at {job['trigger_time']})[/green]")

    def handle_list_reminders(self):
        rems = self.reminders.list_reminders()
        if not rems:
            console.print("[dim]No pending reminders.[/dim]")
            return

        table = Table(title="⏰ Pending Reminders", border_style="yellow")
        table.add_column("ID", style="dim", justify="right")
        table.add_column("Task", style="bold white")
        table.add_column("Scheduled For", style="cyan")

        for r in rems:
            table.add_row(str(r["id"]), r["task"], r["trigger_time"])
        console.print(table)

    def handle_show_memory(self):
        summary = self.memory.get_profile_summary()
        console.print(Panel(summary, title="🧠 N.A.N.I. Memory & Profile", border_style="green"))

    def handle_council(self, question: str):
        if not question:
            console.print("[red]Usage: /council <complex question or technical topic>[/red]")
            return

        console.print(f"\n[cyan]🏛️  Convening Multi-AI Council on: '[bold white]{question}[/bold white]'...[/cyan]")
        console.print("[dim]Consulting: DeepSeek-R1, Llama 3.3 70B, Qwen 2.5 Coder, Gemini 2.0 Flash in parallel...[/dim]\n")

        with console.status("[cyan]Council is deliberating & cross-examining arguments...[/cyan]"):
            result = asyncio.run(self.council.convene(question))

        # Show models consulted
        if result.get("models_consulted"):
            models_str = ", ".join(result["models_consulted"])
            console.print(f"[green]✓ Deliberations collected from: [bold]{models_str}[/bold][/green]\n")

        # Render Gold-Standard Master Answer
        console.print(Panel(
            Markdown(result["master_answer"]),
            title="⚡ Multi-AI Council Consensus & Master Truth",
            border_style="magenta",
            padding=(1, 2)
        ))

    def handle_rotator_status(self):
        summary = self.engine.rotator.get_status_summary()
        table = Table(title="🔄 Free Token Rotator: Provider Pool Status", border_style="cyan")
        table.add_column("Provider", style="bold yellow")
        table.add_column("Target Model", style="white")
        table.add_column("Status", style="bold")
        table.add_column("Total Calls", justify="right", style="cyan")
        table.add_column("Failovers/Errors", justify="right", style="red")

        for s in summary:
            status_style = "green" if s["state"] == "Ready" else ("yellow" if s["state"] == "Cooldown" else "dim")
            table.add_row(
                s["provider"],
                s["model"],
                f"[{status_style}]{s['state']}[/{status_style}]",
                str(s["calls"]),
                str(s["errors"])
            )
        console.print(table)
        console.print("[dim cyan]Note: When a provider hits rate limit (HTTP 429), N.A.N.I. automatically fails over to the next provider.[/dim cyan]\n")

    def show_help(self):
        table = Table(title="🛠️ N.A.N.I. Command Matrix", border_style="bright_cyan")
        table.add_column("Command", style="bold cyan")
        table.add_column("Description", style="white")

        table.add_row("/council <topic>", "Query 3-4 top AIs in parallel and synthesize verified master consensus")
        table.add_row("/rotator", "View free provider pool status & token failovers")
        table.add_row("/battery", "Check laptop battery percentage and AC charging status")
        table.add_row("/see [question]", "Capture and visually analyze what is currently on screen")
        table.add_row("/volume <0-100>", "Adjust laptop speaker volume")
        table.add_row("/mute", "Toggle audio mute")
        table.add_row("/brightness <10-100>", "Adjust laptop display brightness")
        table.add_row("/lock", "Immediately lock the Linux desktop session")
        table.add_row("/screenshot", "Capture laptop screen and save to /tmp/nani")
        table.add_row("/radar [query]", "Scan trending AI & systems repositories on GitHub")
        table.add_row("/inspect <owner/repo>", "Deep-systems architectural dissection of a repository")
        table.add_row("/research <topic>", "Multi-layered 'Why?' research report on any topic")
        table.add_row("/remind <min> <text>", "Set a reminder with Linux desktop notification")
        table.add_row("/reminders", "List all active reminders")
        table.add_row("/stats", "Live Linux telemetry (CPU, RAM, Kernel)")
        table.add_row("/memory", "View N.A.N.I.'s memory and creator profile")
        table.add_row("/help", "Show this command menu")
        table.add_row("/exit", "Shutdown N.A.N.I.")
        console.print(table)

    def chat_loop(self):
        self.print_banner()
        self.show_stats()
        console.print("\n[bold cyan]N.A.N.I. Online.[/bold cyan] Type a question or use [bold white]/help[/bold white] to see commands.\n")

        try:
            while True:
                user_input = console.input("[bold cyan]NANI ❯ [/bold cyan]").strip()
                if not user_input:
                    continue

                if user_input in ("/exit", "exit", "quit"):
                    console.print("[dim cyan]Shutting down N.A.N.I. systems. Standby.[/dim cyan]")
                    self.reminders.shutdown()
                    break

                elif user_input.startswith("/council"):
                    arg = user_input[8:].strip()
                    self.handle_council(arg)

                elif user_input == "/rotator":
                    self.handle_rotator_status()

                elif user_input == "/battery":
                    bat = self.laptop.get_battery_info()
                    ac_str = "🔌 Plugged into AC" if bat["on_ac"] else "🔋 Running on Battery"
                    console.print(f"[bold cyan]Battery Status:[/bold cyan] {bat['percentage']}% ({bat['status']}) | {ac_str}")

                elif user_input.startswith("/volume"):
                    val = user_input[7:].strip()
                    if val.isdigit():
                        res = self.laptop.set_volume(int(val))
                        console.print(f"[green]✓ {res}[/green]")
                    else:
                        console.print("[red]Usage: /volume <0-100>[/red]")

                elif user_input == "/mute":
                    res = self.laptop.toggle_mute()
                    console.print(f"[yellow]✓ {res}[/yellow]")

                elif user_input.startswith("/brightness"):
                    val = user_input[11:].strip()
                    if val.isdigit():
                        res = self.laptop.set_brightness(int(val))
                        console.print(f"[green]✓ {res}[/green]")
                    else:
                        console.print("[red]Usage: /brightness <10-100>[/red]")

                elif user_input == "/lock":
                    res = self.laptop.lock_screen()
                    console.print(f"[cyan]🔒 {res}[/cyan]")

                elif user_input.startswith("/see"):
                    q = user_input[4:].strip() or "What is currently happening on my screen?"
                    console.print(f"\n[cyan]👁️  Capturing display and analyzing screen...[/cyan]")
                    with console.status("[cyan]N.A.N.I. Vision processing screen pixels...[/cyan]"):
                        analysis = self.agent.vision.see_and_analyze(q)
                    console.print(Panel(Markdown(analysis), title="👁️ N.A.N.I. Screen Vision", border_style="bright_blue"))

                elif user_input.startswith("/radar"):
                    arg = user_input[6:].strip()
                    self.handle_radar(arg)

                elif user_input.startswith("/inspect"):
                    arg = user_input[8:].strip()
                    self.handle_inspect(arg)

                elif user_input.startswith("/research"):
                    arg = user_input[9:].strip()
                    self.handle_research(arg)

                elif user_input.startswith("/remind "):
                    arg = user_input[8:].strip()
                    self.handle_remind(arg)

                elif user_input == "/reminders":
                    self.handle_list_reminders()

                elif user_input == "/stats":
                    self.show_stats()

                elif user_input == "/memory":
                    self.handle_show_memory()

                elif user_input == "/help":
                    self.show_help()

                else:
                    # Autonomous Agent processing (Executes tools/actions or converses)
                    self.memory.log_message("user", user_input)
                    console.print(f"\n[bold magenta]N.A.N.I.:[/bold magenta]")
                    
                    with console.status("[cyan]N.A.N.I. evaluating & executing...[/cyan]"):
                        reply = self.agent.process_request(user_input)
                    
                    console.print(Markdown(reply))
                    self.memory.log_message("assistant", reply)

        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim cyan]Interrupted. N.A.N.I. offline.[/dim cyan]")
            self.reminders.shutdown()
