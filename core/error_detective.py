"""
VibeGuard — Error Detective
Context-aware error diagnosis that cross-references PROJECT_MEMORY.md.
"""

import re
import sys
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.syntax import Syntax

console = Console()


# ─── Error Pattern Database ──────────────────────────────────────────────────

ERROR_PATTERNS = [
    # Python
    {
        "regex": r"ModuleNotFoundError: No module named '([^']+)'",
        "type": "ImportError",
        "lang": "Python",
        "fix": lambda m: (
            f"Run: `pip install {m.group(1).split('.')[0]}`\n"
            f"If it's a local module, check your sys.path or __init__.py files."
        ),
    },
    {
        "regex": r"AttributeError: '([^']+)' object has no attribute '([^']+)'",
        "type": "AttributeError",
        "lang": "Python",
        "fix": lambda m: (
            f"The object of type `{m.group(1)}` doesn't have attribute `{m.group(2)}`.\n"
            f"Check the class definition — the attribute might be misspelled, or added after __init__."
        ),
    },
    {
        "regex": r"TypeError: ([^\n]+) takes (\d+) positional argument[s]? but (\d+) (?:was|were) given",
        "type": "TypeError",
        "lang": "Python",
        "fix": lambda m: (
            f"`{m.group(1)}` expects {m.group(2)} argument(s) but got {m.group(3)}.\n"
            f"Check call sites — a `self` param may be missing, or you're passing too many args."
        ),
    },
    {
        "regex": r"IndentationError: ([^\n]+) \(([^,]+), line (\d+)\)",
        "type": "IndentationError",
        "lang": "Python",
        "fix": lambda m: (
            f"Bad indentation in `{m.group(2)}` at line {m.group(3)}.\n"
            f"Check for mixed tabs and spaces. Set your editor to use 4 spaces."
        ),
    },
    {
        "regex": r"KeyError: '([^']+)'",
        "type": "KeyError",
        "lang": "Python",
        "fix": lambda m: (
            f"Key `{m.group(1)}` not found in dict.\n"
            f"Use `.get('{m.group(1)}', default)` for safe access, or check the dict structure."
        ),
    },
    {
        "regex": r"FileNotFoundError: \[Errno 2\] No such file or directory: '([^']+)'",
        "type": "FileNotFoundError",
        "lang": "Python",
        "fix": lambda m: (
            f"File `{m.group(1)}` doesn't exist.\n"
            f"Check the path — it may be relative to the wrong working directory."
        ),
    },
    # JavaScript / Node
    {
        "regex": r"Cannot find module '([^']+)'",
        "type": "ImportError",
        "lang": "JavaScript/Node",
        "fix": lambda m: (
            f"Module `{m.group(1)}` not found.\n"
            f"Run: `npm install {m.group(1).lstrip('./')}` — or check the import path."
        ),
    },
    {
        "regex": r"TypeError: Cannot read propert(?:y|ies) (?:'([^']+)'|of) (?:undefined|null)",
        "type": "NullReference",
        "lang": "JavaScript",
        "fix": lambda m: (
            f"Accessing a property on `undefined` or `null`.\n"
            f"Add a null-check: `if (obj) {{ obj.{m.group(1) if m.group(1) else 'prop'} }}` "
            f"or use optional chaining: `obj?.{m.group(1) if m.group(1) else 'prop'}`."
        ),
    },
    {
        "regex": r"ReferenceError: ([^\s]+) is not defined",
        "type": "ReferenceError",
        "lang": "JavaScript",
        "fix": lambda m: (
            f"`{m.group(1)}` is not defined in scope.\n"
            f"Check spelling, import statements, or variable hoisting issues."
        ),
    },
    {
        "regex": r"SyntaxError: ([^\n]+)",
        "type": "SyntaxError",
        "lang": "JavaScript",
        "fix": lambda m: (
            f"Syntax error: {m.group(1)}\n"
            f"Check for missing brackets, commas, or semicolons near the reported line."
        ),
    },
    # General / HTTP
    {
        "regex": r"ECONNREFUSED (\d+\.\d+\.\d+\.\d+):(\d+)",
        "type": "ConnectionRefused",
        "lang": "Network",
        "fix": lambda m: (
            f"Connection refused to {m.group(1)}:{m.group(2)}.\n"
            f"Is your server running on that port? Check `netstat -an | findstr {m.group(2)}`."
        ),
    },
    {
        "regex": r"ETIMEDOUT",
        "type": "Timeout",
        "lang": "Network",
        "fix": lambda _: (
            "Network timeout — the remote host didn't respond in time.\n"
            "Check your network connection, firewall rules, or API rate limits."
        ),
    },
]


def _extract_file_refs(error_text: str) -> list[str]:
    """Extract file references from stack traces."""
    refs = []
    # Python style: File "path/to/file.py", line N
    python_refs = re.findall(r'File "([^"]+)", line (\d+)', error_text)
    for path, line in python_refs:
        refs.append(f"{path}:{line}")
    # Node style: at ... (path/to/file.js:N:M)
    node_refs = re.findall(r'\(([^)]+\.(?:js|ts|jsx|tsx)):(\d+):\d+\)', error_text)
    for path, line in node_refs:
        refs.append(f"{path}:{line}")
    return list(dict.fromkeys(refs))  # deduplicate, preserve order


def _load_memory(root: Path) -> Optional[str]:
    """Load PROJECT_MEMORY.md if it exists."""
    mem_path = root / "PROJECT_MEMORY.md"
    if mem_path.exists():
        return mem_path.read_text(encoding="utf-8")
    return None


def _cross_reference_memory(error_text: str, memory: str) -> list[str]:
    """Find memory entries relevant to the error."""
    clues = []
    # Extract identifiers from error (camelCase, snake_case, file names)
    identifiers = re.findall(r'\b([a-zA-Z_][a-zA-Z0-9_]{3,})\b', error_text)
    # Find which ones appear in memory doc
    for ident in set(identifiers):
        if len(ident) < 4:
            continue
        if ident in memory and ident not in ("File", "line", "Error", "TypeError"):
            # Find the line in memory
            for i, mline in enumerate(memory.splitlines()):
                if ident in mline and mline.strip():
                    clues.append(f"  Memory hit → `{ident}` mentioned at: {mline.strip()[:100]}")
                    break
    return clues[:5]  # top 5 cross-refs


def diagnose(error_text: str, target_dir: Optional[str] = None) -> None:
    """
    Analyze error text and provide context-aware diagnosis.
    """
    root = Path(target_dir) if target_dir else Path.cwd()
    memory = _load_memory(root)

    console.print(f"\n[bold red]🔍 VibeGuard Error Detective[/bold red]\n")

    # Try to match known patterns
    matched = []
    for pattern in ERROR_PATTERNS:
        m = re.search(pattern["regex"], error_text, re.IGNORECASE | re.MULTILINE)
        if m:
            matched.append((pattern, m))

    # Display error input
    console.print(Panel(
        Syntax(error_text[:1000], "text", theme="monokai", line_numbers=False),
        title="[bold]Input Error[/bold]",
        border_style="red",
        padding=(1, 2),
    ))

    if not matched:
        console.print("\n[yellow]⚠️  No known error pattern matched.[/yellow]")
        console.print("[dim]Tip: Try pasting the full stack trace for better analysis.[/dim]")
    else:
        for pattern, m in matched:
            fix_text = pattern["fix"](m)
            panel_content = Text()
            panel_content.append(f"Type: ", style="bold")
            panel_content.append(f"{pattern['type']} ({pattern['lang']})\n\n", style="cyan")
            panel_content.append("🔧 Suggested Fix:\n", style="bold green")
            panel_content.append(fix_text, style="white")
            console.print(Panel(
                panel_content,
                title="[bold green]💡 Diagnosis[/bold green]",
                border_style="green",
                padding=(1, 2),
            ))

    # File references from stack trace
    refs = _extract_file_refs(error_text)
    if refs:
        console.print("\n[bold cyan]📍 Stack Trace File References:[/bold cyan]")
        for ref in refs[:8]:
            console.print(f"   [dim]→[/dim] [yellow]{ref}[/yellow]")

    # Cross-reference with project memory
    if memory:
        clues = _cross_reference_memory(error_text, memory)
        if clues:
            console.print("\n[bold magenta]🧠 PROJECT_MEMORY.md Cross-Reference:[/bold magenta]")
            for clue in clues:
                console.print(f"   [magenta]{clue}[/magenta]")
    else:
        console.print("\n[dim]💡 Tip: Run `vibeguard scan` first to enable memory cross-referencing.[/dim]")

    # AI prompt suggestion
    console.print("\n[bold blue]🤖 Paste this into your AI:[/bold blue]")
    ai_prompt = _generate_ai_prompt(error_text, matched, refs)
    console.print(Panel(
        ai_prompt,
        border_style="blue",
        padding=(1, 2),
    ))


def _generate_ai_prompt(error_text: str, matched: list, refs: list[str]) -> str:
    lines = ["I have this error in my project:"]
    lines.append("```")
    lines.append(error_text[:500])
    lines.append("```")
    if matched:
        pattern, m = matched[0]
        lines.append(f"\nThis appears to be a `{pattern['type']}` in {pattern['lang']}.")
    if refs:
        lines.append(f"\nRelevant files from stack trace: {', '.join(refs[:3])}")
    lines.append("\nPlease help me fix this. Show me the exact code change needed.")
    return "\n".join(lines)


def run_diagnose(error_text: str, target_dir: Optional[str] = None) -> None:
    """Entry point for the CLI."""
    diagnose(error_text, target_dir)
