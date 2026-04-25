#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VibeGuard -- AI-Native Developer Guardrail & Memory Agent

Usage:
    python vibeguard.py init       -- Initialize VibeGuard in this project
    python vibeguard.py scan       -- Scan codebase -> generate PROJECT_MEMORY.md
    python vibeguard.py guard      -- Watch for regressions (snapshot diff)
    python vibeguard.py diagnose   -- Analyze an error message
    python vibeguard.py compress   -- Compress codebase for AI context windows
    python vibeguard.py score      -- Health score (1-10,000)
    python vibeguard.py status     -- Quick project status overview
    python vibeguard.py build      -- Build project from prompt
"""

import sys
import io
import click
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from core.memory_engine import run_scan
from core.change_guardian import run_guard
from core.error_detective import run_diagnose
from core.context_compressor import run_compress
from core.regression_tracker import run_score
from core.initializer import run_init
from core.autonomous_agent import run_build

# Force UTF-8 output on Windows to support box-drawing and emoji characters
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if sys.stderr.encoding and sys.stderr.encoding.lower() != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

console = Console(force_terminal=True, highlight=True)

BANNER = """[bold cyan]
+----------------------------------------------+
|  [shield] VibeGuard -- AI Developer Guardrail     |
|  Memory * Guard * Score * Compress * Detect  |
+----------------------------------------------+[/bold cyan]
[dim]  Your AI coding session's senior dev safety net[/dim]
"""


@click.group()
@click.version_option("1.0.0", prog_name="VibeGuard")
def cli():
    """VibeGuard — AI-Native Developer Guardrail & Memory Agent."""
    pass


# ─── init ──────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("path", default=".", type=click.Path(exists=True))
def init(path):
    """Initialize VibeGuard in a project directory.

    Detects your tech stack and generates:
    \b
      • .cursorrules  — Guardrail rules for Cursor AI
      • PROJECT_MEMORY.md  — Scaffold for your project memory
      • .vibeguard/stack.json  — Detected stack config
    """
    console.print(BANNER)
    run_init(path)


# ─── scan ──────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("path", default=".", type=click.Path(exists=True))
def scan(path):
    """Scan codebase and generate/update PROJECT_MEMORY.md.

    Indexes all source files, extracting:
    \b
      • Functions, classes, and their signatures
      • Open TODOs and FIXMEs
      • Entry points and key files
      • Language breakdown stats
    """
    console.print(BANNER)
    run_scan(path)


# ─── guard ─────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("path", default=".", type=click.Path(exists=True))
def guard(path):
    """Watch for regressions between code changes.

    Takes a snapshot of your public API surface, waits for you to make changes,
    then compares and reports any regressions (deleted exports, removed functions).

    Generates AI safety prompts for high-severity findings.
    """
    console.print(BANNER)
    run_guard(path)


# ─── diagnose ──────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--error", "-e", default=None, help="Error text to analyze (inline)")
@click.option("--file", "-f", "error_file", default=None,
              type=click.Path(exists=True), help="File containing error/stack trace")
@click.argument("path", default=".", type=click.Path(exists=True))
def diagnose(error, error_file, path):
    """Context-aware error diagnosis.

    Analyzes error messages and stack traces, cross-references with PROJECT_MEMORY.md,
    and suggests targeted fixes. Also generates an AI prompt to paste into Cursor/Claude.

    \b
    Examples:
      vibeguard diagnose -e "ModuleNotFoundError: No module named 'requests'"
      vibeguard diagnose -f error.log
      vibeguard diagnose   (interactive — paste error then Ctrl+D)
    """
    console.print(BANNER)
    if error_file:
        error_text = Path(error_file).read_text(encoding="utf-8")
    elif error:
        error_text = error
    else:
        console.print("[dim]Paste your error/stack trace below, then press Ctrl+D (or Ctrl+Z on Windows):[/dim]\n")
        try:
            lines = []
            while True:
                try:
                    line = input()
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

    run_diagnose(error_text, path)


# ─── compress ──────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--output", "-o", default=None, help="Output file path (default: COMPRESSED_CONTEXT.txt)")
def compress(path, output):
    """Compress codebase for AI context windows (up to 70% token savings).

    Strips comments, collapses blank lines, and truncates long strings.
    Outputs a single COMPRESSED_CONTEXT.txt file ready to paste into your AI.
    """
    console.print(BANNER)
    run_compress(path, output)


# ─── score ─────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("path", default=".", type=click.Path(exists=True))
def score(path):
    """Project health score on the 1–10,000 point scale.

    Evaluates:
    \b
      • Documentation coverage  (2,000 pts)
      • TODO density             (2,000 pts)
      • Import health            (1,500 pts)
      • Function complexity      (1,500 pts)
      • Test coverage            (1,500 pts)
      • Code organization        (1,000 pts)
      • Entry point clarity        (500 pts)
    """
    console.print(BANNER)
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

    console.print("[bold]📋 VibeGuard Status[/bold]\n")

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
        age_str = f"{age.days}d {age.seconds//3600}h ago" if age.days else f"{age.seconds//3600}h {(age.seconds%3600)//60}m ago"
        console.print(f"\n  [dim]PROJECT_MEMORY.md last updated: {age_str}[/dim]")
        if age.days >= 1:
            console.print(f"  [yellow]⚠️  Memory may be stale — run `vibeguard scan` to refresh[/yellow]")

    console.print()
    from core.regression_tracker import run_score
    run_score(path)


@cli.command()
@click.argument("prompt", type=str)
@click.option("--target-dir", type=click.Path(file_okay=False, dir_okay=True), default=".", help="Target directory for the project")
def build(prompt: str, target_dir: str):
    """
    [AUTONOMOUS] Build an entire project from a single prompt.
    Example: vibeguard build "Create a real estate landing page in Next.js"
    """
    console.print(BANNER)
    run_build(prompt, target_dir)


# ─── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cli()
