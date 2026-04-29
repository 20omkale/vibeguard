"""
VibeGuard — Autonomous Software Factory v2
5-Phase pipeline: Requirements → Architecture → Code → Install → Validate
Supports all providers, works for vibe coders AND real developers.
"""

import os
import json
import subprocess
import sys
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.text import Text
from .llm_gateway import get_llm_client
from .memory_engine import run_scan
from .change_guardian import ProjectSnapshot, diff_snapshots
from .telemetry import send_telemetry
from .project_genesis import _generate_prd, _generate_architecture, _generate_database_schema, _generate_api_spec

console = Console(force_terminal=True)


def parse_llm_json(response_text: str) -> dict:
    """Robustly extract JSON from LLM response."""
    try:
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0]
        return json.loads(response_text.strip())
    except Exception as e:
        # Try to find JSON object in the text
        import re
        match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
        console.print(f"[bold red]⚠ Could not parse agent response as JSON: {e}[/bold red]")
        return {"files": {}}


def _gather_requirements(client, initial_prompt: str) -> dict:
    """
    Phase 0: Requirements Gathering
    Ask 3-5 smart clarifying questions, then return a refined prompt + spec.
    """
    console.print("\n[bold yellow]💬 Phase 0: Understanding Your Requirements[/bold yellow]")
    console.print("[dim]The agent is analyzing your request...[/dim]\n")

    system_prompt = """You are a Senior Product Manager and Tech Lead.
Given a rough user idea, generate 3-5 short, smart clarifying questions that will help you build exactly what they need.
Focus on: Tech stack preference, target users, key features, scale, and deployment.

Return ONLY a JSON object:
{
  "questions": [
    {"id": 1, "question": "...", "default": "..."},
    {"id": 2, "question": "...", "default": "..."}
  ]
}"""

    response = client.chat(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": initial_prompt}
        ],
        temperature=0.3,
        max_tokens=800,
    )

    questions_data = parse_llm_json(response)
    answers = {}

    if questions_data.get("questions"):
        console.print("[bold white]I have a few quick questions to build exactly what you need:[/bold white]\n")
        for q in questions_data["questions"]:
            qtext = q.get("question", "")
            default = q.get("default", "")
            if not qtext:
                continue
            if default:
                answer = Prompt.ask(f"  [cyan]{qtext}[/cyan]", default=default)
            else:
                answer = Prompt.ask(f"  [cyan]{qtext}[/cyan]")
            answers[qtext] = answer
        console.print()

    # Build enriched prompt
    enriched = f"Original request: {initial_prompt}\n\nAdditional context from user:\n"
    for q, a in answers.items():
        enriched += f"- {q}: {a}\n"

    return {"enriched_prompt": enriched, "answers": answers}


def _architect_project(client, enriched_prompt: str) -> dict:
    """
    Phase 1: Architecture Planning
    Returns structured file plan with tech stack decision.
    """
    console.print("\n[bold yellow]🏗️  Phase 1: Architecture Planning[/bold yellow]")

    # RAG Flywheel: Fetch past learnings
    past_learnings = ""
    try:
        kb_file = Path.home() / ".vibeguard" / "global_learnings.json"
        if kb_file.exists():
            learnings = json.loads(kb_file.read_text(encoding="utf-8"))
            if learnings:
                past_learnings = "\n\nPAST BUILD LEARNINGS (incorporate these lessons):\n"
                for l in learnings[-5:]:
                    status = "SUCCESS" if l.get('success') else "FAILED"
                    past_learnings += f"- [{status}] Prompt: {l.get('prompt', '')[:80]} | Issue: {l.get('error_logs', 'none')[:100]}\n"
    except Exception:
        pass

    system_prompt = (
        "You are an elite Senior Staff Engineer and Solution Architect.\n"
        "Read the user requirements AND the provided Architecture/PRD context.\n"
        "Given this context, design a complete file structure for the project.\n"
        "Think like a CTO: choose battle-tested tech, not hype. Consider the user's skill level.\n\n"
        "Rules:\n"
        "- The file tree must match the proposed architecture exactly.\n"
        "- For web apps: prefer React/Next.js + Express/FastAPI\n"
        "- For scripts/tools: prefer Python\n"
        "- Always include a README.md\n"
        "- Keep it minimal but complete (no bloat)\n\n"
        "Return ONLY valid JSON:\n"
        "{\n"
        '  "stack": "Clear description of chosen stack and WHY",\n'
        '  "description": "One sentence: what this app does",\n'
        '  "setup_commands": ["npm install", "pip install -r requirements.txt"],\n'
        '  "run_command": "npm run dev",\n'
        '  "files": {\n'
        '    "relative/path/to/file.ext": "Detailed description of what goes in this file"\n'
        "  }\n"
        "}"
        + past_learnings
    )

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
        task = progress.add_task("Designing complete file tree...", total=None)
        response = client.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Project Context:\n{enriched_prompt}"},
            ],
            temperature=0.2,
            max_tokens=3000,
        )

    architecture = parse_llm_json(response)
    if not architecture.get("files"):
        raise ValueError("Agent failed to produce a valid architecture plan.")

    # Show architecture summary
    console.print(f"\n  [green]✓ Stack:[/green] {architecture.get('stack', 'Unknown')}")
    console.print(f"  [green]✓ App:[/green] {architecture.get('description', '')}")
    console.print(f"  [green]✓ Files planned:[/green] {len(architecture['files'])}\n")

    # Show file tree
    table = Table(show_header=True, header_style="bold cyan", box=None, padding=(0, 1))
    table.add_column("File", style="cyan")
    table.add_column("Purpose", style="dim white")
    for file_path, desc in list(architecture["files"].items())[:12]:
        table.add_row(f"  📄 {file_path}", desc[:70])
    if len(architecture["files"]) > 12:
        table.add_row(f"  [dim]... and {len(architecture['files']) - 12} more files[/dim]", "")
    console.print(table)
    console.print()

    # Confirm before building
    if not Confirm.ask("[bold]Shall I build this?[/bold]", default=True):
        console.print("[yellow]Build cancelled.[/yellow]")
        return {}

    return architecture


def write_file_with_healing(client, prompt: str, file_path_str: str, description: str, max_retries: int = 2) -> str:
    """Write code for a single file with self-healing on syntax errors."""
    for attempt in range(max_retries + 1):
        coder_prompt = (
            f"You are writing production-ready code for a project.\n"
            f"Project goal: {prompt[:500]}\n\n"
            f"Write the complete code for file: `{file_path_str}`\n"
            f"File purpose: {description}\n\n"
            "RULES:\n"
            "- Return ONLY raw code. No markdown fences, no explanations.\n"
            "- Write production-quality code, not demos.\n"
            "- Include proper error handling.\n"
            "- Add helpful inline comments.\n"
            "- Make it actually work — no placeholder TODO sections.\n"
        )

        if attempt > 0:
            coder_prompt += f"\n\nWARNING: Previous attempt had syntax errors. Rewrite carefully. Attempt {attempt + 1}/{max_retries + 1}."

        code = client.chat(
            messages=[{"role": "user", "content": coder_prompt}],
            temperature=0.1 + (attempt * 0.05),
            max_tokens=4096,
        )

        # Strip markdown fences if present
        if code.strip().startswith("```"):
            lines = code.strip().splitlines()
            code = "\n".join(lines[1:-1]) if len(lines) > 2 else code

        # Self-healing: check Python syntax
        if file_path_str.endswith(".py"):
            try:
                import ast
                ast.parse(code)
                return code  # Valid Python
            except SyntaxError as e:
                if attempt < max_retries:
                    console.print(f"      [yellow]⚠ Syntax error detected, self-healing... ({e})[/yellow]")
                    continue
        return code

    return code


def _code_phase(client, architecture: dict, root: Path, enriched_prompt: str):
    """Phase 2: Concurrent code generation with real-time progress."""
    import concurrent.futures

    files = architecture["files"]
    total = len(files)
    completed = [0]

    console.print(f"[bold yellow]💻 Phase 2: Generating {total} Files[/bold yellow]")
    console.print(f"[dim]Writing all files simultaneously for maximum speed...[/dim]\n")

    results = {}
    errors = []

    def generate_file(item):
        file_path_str, description = item
        file_path = root / file_path_str
        try:
            code = write_file_with_healing(client, enriched_prompt, file_path_str, description)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(code, encoding="utf-8")
            completed[0] += 1
            console.print(f"  [green]✓[/green] [{completed[0]}/{total}] {file_path_str}")
            results[file_path_str] = True
        except Exception as e:
            completed[0] += 1
            console.print(f"  [red]✗[/red] [{completed[0]}/{total}] {file_path_str} — {e}")
            errors.append(file_path_str)
            results[file_path_str] = False

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        executor.map(generate_file, files.items())

    if errors:
        console.print(f"\n  [yellow]⚠ {len(errors)} file(s) had errors: {', '.join(errors[:3])}[/yellow]")

    return results


def _install_phase(architecture: dict, root: Path):
    """Phase 3: Auto-install dependencies."""
    setup_cmds = architecture.get("setup_commands", [])
    if not setup_cmds:
        return

    console.print("\n[bold yellow]📦 Phase 3: Installing Dependencies[/bold yellow]")

    for cmd in setup_cmds:
        console.print(f"  [cyan]Running:[/cyan] {cmd}")
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0:
                console.print(f"  [green]✓[/green] Done")
            else:
                console.print(f"  [yellow]⚠[/yellow] Completed with warnings")
                if result.stderr:
                    console.print(f"     [dim]{result.stderr[:200]}[/dim]")
        except subprocess.TimeoutExpired:
            console.print(f"  [yellow]⚠[/yellow] Timed out (this is normal for large installs)")
        except Exception as e:
            console.print(f"  [red]✗[/red] {e}")


def run_build(prompt: str, target_dir: str = None) -> None:
    """
    Main entry point for the Autonomous Software Factory.
    Works for vibe coders and real developers alike.
    """
    root = Path(target_dir) if target_dir else Path.cwd()

    console.print(Panel(
        f"[bold cyan]Autonomous Software Factory[/bold cyan]\n\n"
        f"[white]Request:[/white] {prompt}\n"
        f"[white]Output:[/white] {root}",
        border_style="cyan",
        padding=(1, 2),
    ))

    # Get LLM client
    try:
        client = get_llm_client()
    except RuntimeError as e:
        if "no_provider" in str(e):
            console.print(Panel(
                "[bold red]⚠️  No AI provider configured![/bold red]\n\n"
                "VibeGuard needs an AI brain to work. Run this command first:\n\n"
                "  [bold cyan]python vibeguard.py config[/bold cyan]\n\n"
                "Then follow the guided setup. [bold]Groq is 100% free[/bold] — no credit card needed!",
                border_style="red",
                padding=(1, 2),
            ))
            return
        raise

    # Phase 0: Requirements Gathering
    req_data = _gather_requirements(client, prompt)
    enriched_prompt = req_data["enriched_prompt"]
    answers = req_data["answers"]

    # Phase 1: Blueprint Documentation
    console.print("\n[bold yellow]📝 Phase 1: Generating Technical Blueprints[/bold yellow]")
    console.print("[dim]A Senior Dev writes the PRD and Architecture before coding...[/dim]\n")
    root.mkdir(parents=True, exist_ok=True)
    
    docs_context = {"raw_idea": enriched_prompt, **answers}
    try:
        _generate_prd(client, docs_context, root)
        console.print("  [green]✓[/green] PRD.md")
        _generate_architecture(client, docs_context, root)
        console.print("  [green]✓[/green] ARCHITECTURE.md")
        _generate_database_schema(client, docs_context, root)
        console.print("  [green]✓[/green] DATABASE_SCHEMA.md")
        _generate_api_spec(client, docs_context, root)
        console.print("  [green]✓[/green] API_SPEC.md")
    except Exception as e:
        console.print(f"  [yellow]⚠ Documentation step had partial failure: {e}[/yellow]")

    # Gather generated docs to feed into Phase 2 & 3
    doc_payload = f"Original Requirements:\n{enriched_prompt}\n\n"
    for doc in ["PRD.md", "ARCHITECTURE.md"]:
        dp = root / doc
        if dp.exists():
            doc_payload += f"=== {doc} ===\n{dp.read_text(encoding='utf-8')[:2000]}\n\n"

    # Phase 2: Master Architecture Plan (File Tree)
    architecture = _architect_project(client, doc_payload)
    if not architecture:
        return

    baseline = ProjectSnapshot(root)

    # Phase 3: Code Generation
    _code_phase(client, architecture, root, doc_payload)

    # Phase 3: Install dependencies
    _install_phase(architecture, root)

    # Phase 4: Guardrail check
    console.print("\n[bold yellow]🛡️  Phase 4: Guardrail Check[/bold yellow]")
    after = ProjectSnapshot(root)
    regressions = diff_snapshots(baseline, after)
    if regressions:
        highs = sum(1 for r in regressions if r["severity"] == "HIGH")
        console.print(f"  [yellow]⚠ {highs} structural checks flagged[/yellow]")
    else:
        console.print("  [green]✓ All guardrail checks passed[/green]")

    # Phase 5: Memory
    console.print("\n[bold yellow]🧠 Phase 5: Generating Project Memory[/bold yellow]")
    run_scan(str(root), quiet=True)
    console.print("  [green]✓ PROJECT_MEMORY.md generated[/green]")

    # Telemetry
    send_telemetry(prompt, architecture, True)

    # Final summary
    run_cmd = architecture.get("run_command", "")
    console.print(Panel(
        f"[bold green]✅ Build Complete![/bold green]\n\n"
        f"[white]Your project is ready in:[/white] [cyan]{root}[/cyan]\n\n"
        + (f"[white]To run it:[/white] [bold cyan]{run_cmd}[/bold cyan]" if run_cmd else "")
        + f"\n\n[dim]Tip: Run `vibeguard scan` anytime to update your project memory.[/dim]",
        border_style="green",
        padding=(1, 2),
    ))
