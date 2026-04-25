"""
VibeGuard — Change Guardian
Watches for file changes, detects regressions, and generates AI safety prompts.
"""

import os
import ast
import sys
import time
import threading
from pathlib import Path
from typing import Optional
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.text import Text

console = Console()

WATCH_EXTENSIONS = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs"}
IGNORE_DIRS = {"node_modules", "__pycache__", ".git", "dist", "build", ".next", "venv"}


# ─── Snapshot ─────────────────────────────────────────────────────────────────

def _snapshot_python_exports(path: Path) -> set[str]:
    """Get all top-level names (functions, classes, variables) from a Python file."""
    exports = set()
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                exports.add(node.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        exports.add(target.id)
    except Exception:
        pass
    return exports


def _snapshot_js_exports(path: Path) -> set[str]:
    """Extract exported names from JS/TS files (basic heuristic)."""
    exports = set()
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line.startswith(("export function ", "export class ", "export const ", "export let ",
                                "export default function", "module.exports")):
                parts = line.split()
                if len(parts) >= 3:
                    name = parts[2].split("(")[0].split("=")[0].strip()
                    if name and name.isidentifier():
                        exports.add(name)
            elif line.startswith("export default ") and not line.startswith("export default function"):
                name = line.replace("export default", "").replace(";", "").strip()
                if name and name.isidentifier():
                    exports.add(name)
    except Exception:
        pass
    return exports


def _get_exports(path: Path) -> set[str]:
    ext = path.suffix.lower()
    if ext == ".py":
        return _snapshot_python_exports(path)
    elif ext in (".js", ".ts", ".jsx", ".tsx"):
        return _snapshot_js_exports(path)
    return set()


def _get_imports(path: Path) -> set[str]:
    """Extract imported module names."""
    imports = set()
    try:
        if path.suffix == ".py":
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.add(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.add(node.module)
        else:
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if line.startswith("import ") or "require(" in line:
                    imports.add(line[:100])
    except Exception:
        pass
    return imports


class ProjectSnapshot:
    """A snapshot of the project's public API surface."""

    def __init__(self, root: Path):
        self.root = root
        self.taken_at = datetime.now()
        self.exports: dict[str, set[str]] = {}
        self.imports: dict[str, set[str]] = {}
        self._collect()

    def _collect(self):
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not d.startswith(".")]
            for fname in filenames:
                fpath = Path(dirpath) / fname
                if fpath.suffix.lower() not in WATCH_EXTENSIONS:
                    continue
                rel = str(fpath.relative_to(self.root))
                self.exports[rel] = _get_exports(fpath)
                self.imports[rel] = _get_imports(fpath)


def diff_snapshots(before: ProjectSnapshot, after: ProjectSnapshot) -> list[dict]:
    """Compare two snapshots and return a list of regression findings."""
    regressions = []

    all_files = set(before.exports.keys()) | set(after.exports.keys())
    for rel_path in all_files:
        b_exports = before.exports.get(rel_path, set())
        a_exports = after.exports.get(rel_path, set())

        # File deleted
        if rel_path not in after.exports and rel_path in before.exports:
            regressions.append({
                "severity": "HIGH",
                "type": "FILE_DELETED",
                "file": rel_path,
                "detail": f"File `{rel_path}` was deleted. Any imports of this file will break.",
            })
            continue

        # Exports removed
        removed = b_exports - a_exports
        if removed:
            regressions.append({
                "severity": "MEDIUM",
                "type": "EXPORTS_REMOVED",
                "file": rel_path,
                "detail": f"Removed exports from `{rel_path}`: {', '.join(f'`{e}`' for e in sorted(removed))}",
            })

        # New exports (informational)
        added = a_exports - b_exports
        if added:
            regressions.append({
                "severity": "INFO",
                "type": "EXPORTS_ADDED",
                "file": rel_path,
                "detail": f"New exports in `{rel_path}`: {', '.join(f'`{e}`' for e in sorted(added))}",
            })

    return regressions


def _format_regression_table(regressions: list[dict]) -> Table:
    table = Table(show_header=True, header_style="bold magenta", box=None, padding=(0, 1))
    table.add_column("Severity", style="bold", width=10)
    table.add_column("Type", width=20)
    table.add_column("Detail")

    severity_colors = {"HIGH": "red", "MEDIUM": "yellow", "INFO": "cyan"}
    for reg in regressions:
        color = severity_colors.get(reg["severity"], "white")
        table.add_row(
            f"[{color}]{reg['severity']}[/{color}]",
            reg["type"],
            reg["detail"][:100],
        )
    return table


def _generate_safety_prompt(regressions: list[dict]) -> str:
    """Create an AI safety prompt from regression findings."""
    high = [r for r in regressions if r["severity"] == "HIGH"]
    medium = [r for r in regressions if r["severity"] == "MEDIUM"]

    lines = [
        "⚠️ VIBEGUARD SAFETY ALERT — Potential Regressions Detected\n",
        "Before proceeding, please verify the following issues:\n",
    ]
    if high:
        lines.append("🔴 HIGH severity:")
        for r in high:
            lines.append(f"  - {r['detail']}")
    if medium:
        lines.append("\n🟡 MEDIUM severity:")
        for r in medium:
            lines.append(f"  - {r['detail']}")
    lines.append("\nPlease ensure these are intentional changes, not accidental regressions.")
    return "\n".join(lines)


# ─── One-shot diff check ───────────────────────────────────────────────────────

def run_guard(target_dir: Optional[str] = None) -> None:
    """
    Take a snapshot → wait for user to make changes → compare → report.
    """
    root = Path(target_dir) if target_dir else Path.cwd()

    console.print(f"\n[bold yellow]🛡️  VibeGuard Change Guardian[/bold yellow]")
    console.print(f"[dim]Watching: {root}[/dim]\n")

    console.print("[cyan]Taking baseline snapshot...[/cyan]")
    before = ProjectSnapshot(root)
    console.print(f"[green]✓ Snapshot taken[/green] — {len(before.exports)} files indexed")
    console.print("\n[dim]Press [bold]Enter[/bold] after making your changes to compare...[/dim]")

    try:
        input()
    except EOFError:
        time.sleep(2)

    console.print("\n[cyan]Re-scanning for changes...[/cyan]")
    after = ProjectSnapshot(root)

    regressions = diff_snapshots(before, after)

    if not regressions:
        console.print("\n[bold green]✅ No regressions detected! Your changes look clean.[/bold green]")
        return

    highs = sum(1 for r in regressions if r["severity"] == "HIGH")
    mediums = sum(1 for r in regressions if r["severity"] == "MEDIUM")
    infos = sum(1 for r in regressions if r["severity"] == "INFO")

    console.print(f"\n[bold]📋 Change Report[/bold]  "
                  f"[red]{highs} HIGH[/red]  "
                  f"[yellow]{mediums} MEDIUM[/yellow]  "
                  f"[cyan]{infos} INFO[/cyan]\n")

    table = _format_regression_table(regressions)
    console.print(table)

    if highs + mediums > 0:
        console.print("\n[bold blue]🤖 AI Safety Prompt:[/bold blue]")
        safety_prompt = _generate_safety_prompt(regressions)
        console.print(Panel(safety_prompt, border_style="yellow", padding=(1, 2)))
