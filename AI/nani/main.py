"""N.A.N.I. V2 — Entrypoint & Core Runtime CLI
Neural Analytical Network Intelligence (Version 2.0.0 Alpha — Phase 1 Core Runtime)
"""

import sys

from rich.console import Console
from rich.panel import Panel

from nani.config import settings
from nani.core.orchestrator import Orchestrator
from nani.core.task_manager import TaskManager
from nani.memory.database import Database
from nani.memory.journal import ActionJournal
from nani.tools.filesystem import register_filesystem_tools
from nani.tools.git import register_git_tools
from nani.tools.process import register_process_tools
from nani.tools.registry import ToolRegistry
from nani.tools.shell import register_shell_tools
from nani.tools.system_hardware import register_hardware_tools
from nani.tools.web_search import register_web_tools

console = Console()


def create_runtime() -> tuple[TaskManager, ToolRegistry, Orchestrator]:
    """Boots the NANI V2 execution engine."""
    db = Database(settings.db_path)
    journal = ActionJournal(db)
    task_manager = TaskManager(db=db, journal=journal)

    registry = ToolRegistry(journal=journal)
    register_filesystem_tools(registry)
    register_shell_tools(registry)
    register_process_tools(registry)
    register_git_tools(registry)
    register_web_tools(registry)
    register_hardware_tools(registry)

    orchestrator = Orchestrator(
        task_manager=task_manager,
        tool_registry=registry,
        journal=journal,
    )
    return task_manager, registry, orchestrator


def main() -> int:
    console.print(
        Panel(
            f"[bold cyan]⚡ N . A . N . I .   V 2 ⚡[/bold cyan]\n"
            f"[italic bright_white]Neural Analytical Network Intelligence[/italic bright_white]\n"
            f"[dim cyan]v{settings.version} | Mode: {settings.env.value.upper()} | Phase 1 Core Runtime[/dim cyan]",
            border_style="cyan",
        )
    )

    task_manager, registry, _ = create_runtime()
    version = task_manager.db.get_schema_version()
    tools_count = len(registry.list_tools())

    console.print(
        f"[green]✓ Database initialized:[/green] [dim]{settings.db_path} (Schema v{version})[/dim]"
    )
    console.print(
        f"[green]✓ Native tools registered:[/green] [cyan]{tools_count} tools[/cyan] "
        f"[dim]({', '.join(sorted(registry.list_tools().keys()))})[/dim]"
    )
    console.print(
        "[green]✓ Core runtime ready:[/green] TaskManager, ToolRegistry, ActionJournal, Verifier, Orchestrator active.\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
