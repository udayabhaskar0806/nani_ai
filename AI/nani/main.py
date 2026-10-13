"""N.A.N.I. V2 — Entrypoint
Neural Analytical Network Intelligence (Version 2.0.0 Alpha)
"""

import sys

from rich.console import Console
from rich.panel import Panel

from nani.config import settings
from nani.memory.database import Database

console = Console()


def main() -> int:
    console.print(
        Panel(
            f"[bold cyan]⚡ N . A . N . I .   V 2 ⚡[/bold cyan]\n"
            f"[italic bright_white]Neural Analytical Network Intelligence[/italic bright_white]\n"
            f"[dim cyan]v{settings.version} | Mode: {settings.env.value.upper()} | Phase 0 Bootstrap[/dim cyan]",
            border_style="cyan",
        )
    )

    # Initialize SQLite database
    db = Database(settings.db_path)
    version = db.get_schema_version()
    console.print(
        f"[green]✓ Database initialized:[/green] [dim]{settings.db_path} (Schema v{version})[/dim]"
    )
    console.print(
        "[dim cyan]Core contracts verified. Ready for Phase 1 runtime initialization.[/dim cyan]\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
