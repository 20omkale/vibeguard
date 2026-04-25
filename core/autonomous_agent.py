"""
VibeGuard — Autonomous Software Factory
Takes a single prompt and autonomously plans, specs, and builds the project files.
Features Self-Healing and Telemetry.
"""

import os
import json
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from .llm_gateway import get_llm_client
from .memory_engine import run_scan
from .change_guardian import ProjectSnapshot, diff_snapshots
from .telemetry import send_telemetry

console = Console()

def parse_llm_json(response_text: str) -> dict:
    try:
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0]
        return json.loads(response_text.strip())
    except Exception as e:
        console.print(f"[bold red]Failed to parse LLM JSON response: {e}[/bold red]")
        return {"files": {}}

def write_code_with_self_healing(client, model, prompt, file_path_str, description, max_retries=2):
    """Generates code and uses an internal LLM review loop to fix syntax errors."""
    for attempt in range(max_retries + 1):
        coder_prompt = (
            f"You are writing code for a project. The overall goal is: {prompt}\n"
            f"Your current task is to write the complete, production-ready code for the file: {file_path_str}\n"
            f"File purpose: {description}\n"
            "Return ONLY the raw code for this file. No markdown formatting, no explanations."
        )
        
        if attempt > 0:
            coder_prompt += f"\n\nWARNING: Your previous attempt had errors. Please rewrite it carefully."

        code_response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": coder_prompt}],
            temperature=0.1 + (attempt * 0.1), # Increase creativity if stuck
        )
        
        code_content = code_response.choices[0].message.content.strip()
        if code_content.startswith("```"):
            lines = code_content.splitlines()
            if len(lines) > 2:
                code_content = "\n".join(lines[1:-1])
                
        # Basic Syntax Check Heuristic (Self-Healing trigger)
        if file_path_str.endswith(".py"):
            try:
                import ast
                ast.parse(code_content)
                return code_content # Success
            except SyntaxError:
                if attempt == max_retries:
                    return code_content # Give up and return buggy code
                console.print(f"\n    [yellow]⚠ Syntax error detected by Self-Healing loop. Rewriting... (Attempt {attempt+2})[/yellow]")
                continue
                
        return code_content # For non-python files, return immediately

def run_build(prompt: str, target_dir: str = None) -> None:
    root = Path(target_dir) if target_dir else Path.cwd()
    
    console.print(Panel(f"[bold cyan]Autonomous Software Factory[/bold cyan]\nBuilding: {prompt}", border_style="cyan"))
    
    try:
        client, model = get_llm_client()
    except Exception:
        return

    # 1. Architect Phase
    console.print("\n[bold yellow]🏗️  Phase 1: Architecting[/bold yellow]")
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
        progress.add_task("Designing project structure and tech stack...", start=True)
        
        # RAG Flywheel: Fetch past learnings
        past_learnings = ""
        try:
            kb_file = Path.home() / ".vibeguard" / "global_learnings.json"
            if kb_file.exists():
                with open(kb_file, "r", encoding="utf-8") as f:
                    learnings = json.load(f)
                    if learnings:
                        past_learnings = "\n\nPAST LEARNINGS (Avoid previous mistakes):\n"
                        for l in learnings[-3:]: # Grab last 3 attempts
                            status = "SUCCESS" if l['success'] else "FAILED"
                            past_learnings += f"- Prompt: {l['prompt']} | Status: {status} | Error: {l['error_logs']}\n"
        except Exception:
            pass

        system_prompt = (
            "You are an elite Senior Staff Engineer designing a project from scratch.\n"
            "Given the user's idea, decide on the absolute best, modern tech stack.\n"
            "Output your entire architecture plan strictly as a JSON object with this exact format:\n"
            "{\n"
            '  "stack": "The tech stack chosen",\n'
            '  "files": {\n'
            '    "relative/path/to/file1.ext": "Detailed description of what goes in this file"\n'
            "  }\n"
            "}"
            + past_learnings
        )
        
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
        )
        
    architecture = parse_llm_json(response.choices[0].message.content)
    if not architecture or "files" not in architecture:
        console.print("[bold red]Agent failed to design a valid architecture.[/bold red]")
        send_telemetry(prompt, architecture, False, "Architecture parsing failed")
        return
        
    console.print(f"  [green]✓ Stack Selected:[/green] {architecture.get('stack', 'Unknown')}")
    console.print(f"  [green]✓ Files Planned:[/green] {len(architecture['files'])}")

    baseline = ProjectSnapshot(root)

    # 2. Coding Phase
    console.print("\n[bold yellow]💻 Phase 2: Autonomous Coding & Self-Healing[/bold yellow]")
    
    for file_path_str, description in architecture["files"].items():
        file_path = root / file_path_str
        console.print(f"  Writing [cyan]{file_path_str}[/cyan]...")
        
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
            progress.add_task(f"Generating and verifying code for {file_path.name}...", start=True)
            code_content = write_code_with_self_healing(client, model, prompt, file_path_str, description)
        
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(code_content, encoding="utf-8")
        console.print(f"    [green]✓ Done[/green]")

    # 3. Guardrail & Memory Phase
    console.print("\n[bold yellow]🛡️  Phase 3: Guardrail Check[/bold yellow]")
    after = ProjectSnapshot(root)
    regressions = diff_snapshots(baseline, after)
    
    if regressions:
        highs = sum(1 for r in regressions if r["severity"] == "HIGH")
        console.print(f"  [yellow]⚠ Internal checks detected {highs} structural changes.[/yellow]")
    else:
        console.print("  [green]✓ Guardrail checks passed clean.[/green]")
        
    run_scan(str(root), quiet=True)
    
    # 4. Telemetry Phase
    send_telemetry(prompt, architecture, True)
    
    console.print(Panel("[bold green]✅ Project Built Successfully![/bold green]\nYour software factory has completed its run.", border_style="green"))
