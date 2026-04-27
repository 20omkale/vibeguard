#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VibeGuard — AI-Native Developer Platform
Build. Guard. Debug. Fix. End-to-end.

Usage:
    python vibeguard.py          -- Interactive mode (no commands needed!)
    python vibeguard.py config   -- Setup API keys (first-time wizard)
    python vibeguard.py build    -- Build a project from your idea
    python vibeguard.py diagnose -- Paste an error, get the fix
    python vibeguard.py init     -- Add VibeGuard to an existing project
    python vibeguard.py scan     -- Index codebase → PROJECT_MEMORY.md
    python vibeguard.py guard    -- Watch for regressions
    python vibeguard.py compress -- Compress codebase for AI context windows
    python vibeguard.py score    -- Health score (1-10,000)
    python vibeguard.py status   -- Quick project status
"""

import sys
import io
import click
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.rule import Rule
from rich.prompt import Prompt
from rich.columns import Columns

# Force UTF-8 output on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

console = Console(force_terminal=True, highlight=True)

BANNER = """[bold cyan]
+--------------------------------------------------+
|   VibeGuard  --  AI Development Platform         |
|   Build  *  Guard  *  Debug  *  Fix  *  Ship     |
+--------------------------------------------------+[/bold cyan]
[dim]  Your AI senior developer, available 24/7[/dim]
"""


def _check_first_run():
    """Show wizard on first run if not configured."""
    from core.config_manager import is_configured, run_first_time_wizard
    if not is_configured():
        console.print(BANNER)
        console.print(Panel(
            "[bold yellow]First time here! Let's get you set up.[/bold yellow]\n\n"
            "VibeGuard needs an AI provider to work.\n"
            "This is a [bold]one-time setup[/bold] that takes about 60 seconds.",
            border_style="yellow",
            padding=(1, 2),
        ))
        run_first_time_wizard()
        console.print()


@click.group(invoke_without_command=True)
@click.version_option("2.0.0", prog_name="VibeGuard")
@click.pass_context
def cli(ctx):
    """VibeGuard — AI-Native Developer Platform. Build, guard, debug, and ship."""
    if ctx.invoked_subcommand is None:
        # No subcommand — run interactive mode
        _interactive_mode()


# ─── config ────────────────────────────────────────────────────────────────────

@cli.command()
def config():
    """Setup your AI provider and API keys (run this first!)."""
    console.print(BANNER)
    from core.config_manager import run_config_command
    run_config_command()


# ─── build ─────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("prompt", type=str, required=False)
@click.option("--target-dir", "-d", type=click.Path(file_okay=False, dir_okay=True),
              default=".", help="Where to create the project (default: current directory)")
def build(prompt, target_dir):
    """Build a complete project from your idea.

    \b
    Examples:
      vibeguard build "a todo app with React and FastAPI"
      vibeguard build "a Discord bot that tracks stock prices"
      vibeguard build "a REST API for a blog with authentication"
      vibeguard build  (launches interactive mode to type your idea)
    """
    console.print(BANNER)
    _check_first_run()

    if not prompt:
        console.print("\n[bold cyan]What would you like to build today?[/bold cyan]")
        console.print("[dim]Describe your idea in plain English. Be as specific or as vague as you want.[/dim]\n")
        prompt = Prompt.ask("[bold white]>>>[/bold white]")
        if not prompt.strip():
            console.print("[yellow]No idea provided. Exiting.[/yellow]")
            return

    from core.autonomous_agent import run_build
    run_build(prompt.strip(), target_dir)


# ─── diagnose ──────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--error", "-e", default=None, help="Error text to analyze")
@click.option("--file", "-f", "error_file", default=None,
              type=click.Path(exists=True), help="File containing error/stack trace")
@click.argument("path", default=".", type=click.Path(exists=True))
def diagnose(error, error_file, path):
    """Analyze an error and get a precise fix.

    \b
    Examples:
      vibeguard diagnose -e "TypeError: Cannot read property of undefined"
      vibeguard diagnose -f error.log
      vibeguard diagnose  (paste your error interactively)
    """
    console.print(BANNER)
    _check_first_run()

    if error_file:
        error_text = Path(error_file).read_text(encoding="utf-8")
    elif error:
        error_text = error
    else:
        console.print("\n[bold cyan]Paste your error or stack trace below.[/bold cyan]")
        console.print("[dim]Press Enter twice when done, or Ctrl+C to cancel.[/dim]\n")
        lines = []
        try:
            empty_lines = 0
            while True:
                try:
                    line = input()
                    if line == "":
                        empty_lines += 1
                        if empty_lines >= 2:
                            break
                    else:
                        empty_lines = 0
                    lines.append(line)
                except EOFError:
                    break
            error_text = "\n".join(lines)
        except KeyboardInterrupt:
            console.print("\n[yellow]Cancelled.[/yellow]")
            sys.exit(0)

    if not error_text.strip():
        console.print("[red]No error text provided.[/red]")
        sys.exit(1)

    from core.error_detective import run_diagnose
    run_diagnose(error_text, path)


# ─── init ──────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("path", default=".", type=click.Path(exists=True))
def init(path):
    """Initialize VibeGuard in an existing project.

    Detects your tech stack and generates:
    \b
      - .cursorrules       Guardrail rules for Cursor AI
      - PROJECT_MEMORY.md  Scaffold for your project memory
      - .vibeguard/        Stack config and snapshots
    """
    console.print(BANNER)
    from core.initializer import run_init
    run_init(path)


# ─── scan ──────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("path", default=".", type=click.Path(exists=True))
def scan(path):
    """Scan codebase and generate/update PROJECT_MEMORY.md."""
    console.print(BANNER)
    from core.memory_engine import run_scan
    run_scan(path)


# ─── guard ─────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("path", default=".", type=click.Path(exists=True))
def guard(path):
    """Watch for regressions between code changes."""
    console.print(BANNER)
    from core.change_guardian import run_guard
    run_guard(path)


# ─── compress ──────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--output", "-o", default=None, help="Output file path")
def compress(path, output):
    """Compress codebase for AI context windows (up to 70% token savings)."""
    console.print(BANNER)
    from core.context_compressor import run_compress
    run_compress(path, output)


# ─── score ─────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("path", default=".", type=click.Path(exists=True))
def score(path):
    """Project health score on the 1-10,000 scale."""
    console.print(BANNER)
    from core.regression_tracker import run_score
    run_score(path)


# ─── status ────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("path", default=".", type=click.Path(exists=True))
def status(path):
    """Quick project status — scan + score in one shot."""
    console.print(BANNER)
    root = Path(path)
    memory_path = root / "PROJECT_MEMORY.md"
    cursorrules_path = root / ".cursorrules"
    vg_dir = root / ".vibeguard"

    console.print("[bold]Project Status[/bold]\n")
    checks = [
        ("PROJECT_MEMORY.md", memory_path.exists()),
        (".cursorrules", cursorrules_path.exists()),
        (".vibeguard/ config", vg_dir.exists()),
    ]
    for name, ok in checks:
        icon = "[green]✓[/green]" if ok else "[red]✗[/red]"
        console.print(f"  {icon} {name}")

    if memory_path.exists():
        stat = memory_path.stat()
        mtime = __import__("datetime").datetime.fromtimestamp(stat.st_mtime)
        age = __import__("datetime").datetime.now() - mtime
        age_str = f"{age.days}d ago" if age.days else f"{age.seconds//3600}h {(age.seconds%3600)//60}m ago"
        console.print(f"\n  [dim]Memory last updated: {age_str}[/dim]")
        if age.days >= 1:
            console.print("  [yellow]⚠  Memory may be stale — run `vibeguard scan` to refresh[/yellow]")

    console.print()
    from core.regression_tracker import run_score
    run_score(path)


# ─── Interactive Mode ───────────────────────────────────────────────────────────

def _interactive_mode():
    """
    Full interactive TUI for users who run `python vibeguard.py` with no arguments.
    Persona-aware: detects vibe coders vs real developers.
    """
    console.print(BANNER)

    # Check first-time setup
    from core.config_manager import is_configured, run_first_time_wizard, load_config, PROVIDERS
    config = load_config()
    provider = config.get("provider", "")

    if not is_configured():
        console.print(Panel(
            "[bold yellow]Welcome! Looks like this is your first time.[/bold yellow]\n\n"
            "Let me set things up — it takes about 60 seconds.\n"
            "[bold]Groq is completely free[/bold] — no credit card needed.",
            border_style="yellow",
            padding=(1, 2),
        ))
        run_first_time_wizard()
        console.print()
    else:
        pname = PROVIDERS.get(provider, {}).get("name", provider)
        console.print(f"[dim]  AI Provider: {pname}[/dim]\n")

    # Main menu
    console.print("[bold white]What would you like to do?[/bold white]\n")
    console.print("  [bold cyan][1][/bold cyan]  🏗️  [bold]Build a new project[/bold]")
    console.print("       [dim]Describe your idea → agent plans, codes, installs everything[/dim]")
    console.print()
    console.print("  [bold cyan][2][/bold cyan]  🐛  [bold]Debug / Fix an error[/bold]")
    console.print("       [dim]Paste your error → get the exact root cause + fix[/dim]")
    console.print()
    console.print("  [bold cyan][3][/bold cyan]  🛡️  [bold]Protect an existing project[/bold]")
    console.print("       [dim]Initialize memory, guardrails, and regression tracking[/dim]")
    console.print()
    console.print("  [bold cyan][4][/bold cyan]  📊  [bold]Score project health[/bold]")
    console.print("       [dim]Get a 1-10,000 quality score across 7 dimensions[/dim]")
    console.print()
    console.print("  [bold cyan][5][/bold cyan]  ⚙️  [bold]Change AI provider / API keys[/bold]")
    console.print()

    try:
        choice = Prompt.ask("\n[bold white]Select[/bold white]", choices=["1", "2", "3", "4", "5"], default="1")

        if choice == "1":
            console.print("\n[bold cyan]What would you like to build?[/bold cyan]")
            console.print("[dim]Examples: 'a todo app with login', 'a Discord bot', 'a FastAPI backend with auth'[/dim]\n")
            prompt = Prompt.ask("[bold white]Describe your idea[/bold white]")
            if prompt.strip():
                target = Prompt.ask(
                    "\n[bold white]Where should I create it?[/bold white]",
                    default=".",
                )
                console.print()
                from core.autonomous_agent import run_build
                run_build(prompt.strip(), target.strip() or ".")

        elif choice == "2":
            console.print("\n[bold cyan]Paste your error or stack trace.[/bold cyan]")
            console.print("[dim]Press Enter twice when done.[/dim]\n")
            lines = []
            empty_count = 0
            while True:
                try:
                    line = input()
                    if line == "":
                        empty_count += 1
                        if empty_count >= 2:
                            break
                    else:
                        empty_count = 0
                    lines.append(line)
                except EOFError:
                    break

            error_text = "\n".join(lines).strip()
            if error_text:
                console.print("\n[dim]Enter the path to your project (or press Enter for current folder):[/dim]")
                path = Prompt.ask("[bold white]Project path[/bold white]", default=".")
                from core.error_detective import run_diagnose
                run_diagnose(error_text, path)

        elif choice == "3":
            path = Prompt.ask(
                "\n[bold white]Enter path to your project[/bold white]",
                default="."
            )
            from core.initializer import run_init
            from core.memory_engine import run_scan
            run_init(path)
            run_scan(path)

        elif choice == "4":
            path = Prompt.ask(
                "\n[bold white]Enter path to your project[/bold white]",
                default="."
            )
            from core.regression_tracker import run_score
            run_score(path)

        elif choice == "5":
            from core.config_manager import run_config_command
            run_config_command()

    except KeyboardInterrupt:
        console.print("\n\n[yellow]Goodbye! Run `python vibeguard.py` anytime.[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")

    # Prevent terminal from closing when double-clicked as .exe
    if getattr(sys, "frozen", False):
        input("\nPress Enter to exit...")


# ─── Entry Point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cli()
