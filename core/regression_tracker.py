"""
VibeGuard — Regression Tracker & Health Scorer
Scores project health on a 1–10,000 scale and generates benchmark reports.
"""

import os
import ast
import re
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

console = Console()

IGNORE_DIRS = {"node_modules", "__pycache__", ".git", "dist", "build", ".next", "venv", ".venv"}
SOURCE_EXTENSIONS = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java"}
TEST_EXTENSIONS = {".py", ".js", ".ts"}


# ─── Scoring factors (total = 10,000) ────────────────────────────────────────
#
# Category                   Max Points   Weight
# ─────────────────────────────────────────────
# Documentation coverage       2000        20%
# TODO density (inverted)      2000        20%
# Import health                1500        15%
# Function complexity          1500        15%
# Test file ratio              1500        15%
# Code organization            1000        10%
# Entry point clarity           500         5%
# ─────────────────────────────────────────────
# TOTAL                       10,000      100%

MAX_SCORE = 10_000


def _count_functions_python(path: Path) -> tuple[int, int, int]:
    """Returns (total_functions, documented_functions, avg_complexity_proxy)."""
    total = 0
    documented = 0
    complexities = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                total += 1
                if ast.get_docstring(node):
                    documented += 1
                # Complexity proxy: number of branches
                complexity = sum(
                    1 for n in ast.walk(node)
                    if isinstance(n, (ast.If, ast.For, ast.While, ast.Try, ast.ExceptHandler,
                                      ast.With, ast.Assert))
                )
                complexities.append(complexity)
    except Exception:
        pass
    avg_complexity = sum(complexities) / max(len(complexities), 1)
    return total, documented, int(avg_complexity)


def _count_todos(path: Path) -> int:
    try:
        count = 0
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if any(tag in line.upper() for tag in ("TODO", "FIXME", "HACK", "XXX", "BUG")):
                count += 1
        return count
    except Exception:
        return 0


def _has_broken_imports(path: Path) -> bool:
    """Detect obviously broken relative imports (Python only)."""
    if path.suffix != ".py":
        return False
    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.level and node.level > 3:  # Excessive relative depth
                    return True
    except SyntaxError:
        return True  # Syntax errors = broken
    except Exception:
        pass
    return False


def _is_test_file(path: Path) -> bool:
    name = path.name.lower()
    return (
        name.startswith("test_") or
        name.endswith("_test.py") or
        name.endswith(".test.js") or
        name.endswith(".test.ts") or
        name.endswith(".spec.ts") or
        name.endswith(".spec.js") or
        "tests" in str(path).lower()
    )


def compute_score(root: Path) -> dict:
    """Walk the project and compute the 10,000-point health score."""
    stats = {
        "total_source_files": 0,
        "test_files": 0,
        "total_functions": 0,
        "documented_functions": 0,
        "total_todos": 0,
        "broken_import_files": 0,
        "total_lines": 0,
        "avg_complexity": 0,
        "has_readme": False,
        "has_entry_point": False,
        "complexity_sum": 0,
        "complexity_count": 0,
    }

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not d.startswith(".")]
        for fname in filenames:
            fpath = Path(dirpath) / fname
            fname_lower = fname.lower()

            if fname_lower in ("readme.md", "readme.rst", "readme.txt"):
                stats["has_readme"] = True
            if fname_lower in ("main.py", "app.py", "index.js", "index.ts", "main.go", "index.tsx"):
                stats["has_entry_point"] = True

            if fpath.suffix.lower() not in SOURCE_EXTENSIONS:
                continue

            stats["total_source_files"] += 1
            if _is_test_file(fpath):
                stats["test_files"] += 1

            stats["total_todos"] += _count_todos(fpath)
            if _has_broken_imports(fpath):
                stats["broken_import_files"] += 1

            try:
                lines = len(fpath.read_text(encoding="utf-8", errors="ignore").splitlines())
                stats["total_lines"] += lines
            except Exception:
                pass

            if fpath.suffix == ".py":
                total_fn, doc_fn, avg_cx = _count_functions_python(fpath)
                stats["total_functions"] += total_fn
                stats["documented_functions"] += doc_fn
                stats["complexity_sum"] += avg_cx
                stats["complexity_count"] += 1

    if stats["complexity_count"]:
        stats["avg_complexity"] = stats["complexity_sum"] / stats["complexity_count"]

    return stats


def _score_docs(stats: dict) -> int:
    """Documentation coverage score (max 2000)."""
    if stats["total_functions"] == 0:
        return 1000  # No functions = neutral
    ratio = stats["documented_functions"] / stats["total_functions"]
    return round(ratio * 2000)


def _score_todos(stats: dict) -> int:
    """TODO density score (max 2000). Fewer TODOs = higher score."""
    if stats["total_lines"] == 0:
        return 2000
    todo_density = stats["total_todos"] / max(stats["total_lines"] / 100, 1)  # per 100 lines
    # 0 TODOs = 2000, 5+ per 100 lines = 0
    score = max(0, 2000 - round(todo_density * 400))
    return min(2000, score)


def _score_imports(stats: dict) -> int:
    """Import health score (max 1500)."""
    if stats["total_source_files"] == 0:
        return 1500
    broken_ratio = stats["broken_import_files"] / stats["total_source_files"]
    return max(0, round(1500 * (1 - broken_ratio * 3)))


def _score_complexity(stats: dict) -> int:
    """Function complexity score (max 1500). Lower complexity = higher score."""
    avg_cx = stats["avg_complexity"]
    if avg_cx == 0:
        return 1500
    # avg complexity 0–3 = great, 4–6 = ok, 7+ = poor
    if avg_cx <= 2:
        return 1500
    elif avg_cx <= 4:
        return 1200
    elif avg_cx <= 6:
        return 900
    elif avg_cx <= 10:
        return 500
    else:
        return 200


def _score_tests(stats: dict) -> int:
    """Test file ratio score (max 1500)."""
    if stats["total_source_files"] == 0:
        return 750
    ratio = stats["test_files"] / stats["total_source_files"]
    # 20%+ test files = max score
    score = min(1.0, ratio / 0.20) * 1500
    return round(score)


def _score_organization(stats: dict) -> int:
    """Code organization score (max 1000)."""
    score = 500  # base
    if stats["has_readme"]:
        score += 300
    if stats["total_source_files"] > 1:
        score += 200
    return min(1000, score)


def _score_entry_point(stats: dict) -> int:
    """Entry point clarity score (max 500)."""
    return 500 if stats["has_entry_point"] else 200


def compute_final_score(stats: dict) -> dict:
    """Compute all sub-scores and total."""
    scores = {
        "Documentation Coverage": _score_docs(stats),
        "TODO Density": _score_todos(stats),
        "Import Health": _score_imports(stats),
        "Function Complexity": _score_complexity(stats),
        "Test Coverage": _score_tests(stats),
        "Code Organization": _score_organization(stats),
        "Entry Point Clarity": _score_entry_point(stats),
    }
    total = sum(scores.values())
    return {"breakdown": scores, "total": total}


def _health_label(score: int) -> tuple[str, str]:
    """Return (label, color) for a score."""
    if score >= 8000:
        return "🏆 Excellent", "bold green"
    elif score >= 6000:
        return "✅ Good", "green"
    elif score >= 4000:
        return "⚠️  Fair", "yellow"
    elif score >= 2000:
        return "❌ Poor", "red"
    else:
        return "💀 Critical", "bold red"


def run_score(target_dir: Optional[str] = None) -> None:
    root = Path(target_dir) if target_dir else Path.cwd()

    console.print(f"\n[bold magenta]📊 VibeGuard Health Scorer[/bold magenta]")
    console.print(f"[dim]Analyzing: {root}[/dim]\n")

    with Progress(SpinnerColumn(), TextColumn("[cyan]Analyzing codebase...[/cyan]"),
                  console=console, transient=True):
        stats = compute_score(root)

    result = compute_final_score(stats)
    total = result["total"]
    breakdown = result["breakdown"]
    label, color = _health_label(total)
    max_pts = {"Documentation Coverage": 2000, "TODO Density": 2000, "Import Health": 1500,
               "Function Complexity": 1500, "Test Coverage": 1500,
               "Code Organization": 1000, "Entry Point Clarity": 500}

    # Main score panel
    bar_filled = round(total / MAX_SCORE * 30)
    bar_empty = 30 - bar_filled
    bar = "█" * bar_filled + "░" * bar_empty
    console.print(Panel(
        f"[{color}]{total:,} / {MAX_SCORE:,}[/{color}]  {bar}\n[{color}]{label}[/{color}]",
        title="[bold]Project Health Score[/bold]",
        border_style=color.split()[-1],
        padding=(1, 4),
    ))

    # Breakdown table
    table = Table(show_header=True, header_style="bold cyan", box=None, padding=(0, 2))
    table.add_column("Category")
    table.add_column("Score", justify="right")
    table.add_column("Max", justify="right")
    table.add_column("Grade", justify="center")
    table.add_column("Bar")

    for category, score in breakdown.items():
        max_pts_cat = max_pts[category]
        pct = score / max_pts_cat
        grade = "A" if pct >= 0.85 else "B" if pct >= 0.70 else "C" if pct >= 0.50 else "D" if pct >= 0.30 else "F"
        grade_color = {"A": "green", "B": "cyan", "C": "yellow", "D": "red", "F": "bold red"}[grade]
        mini_bar_len = round(pct * 15)
        mini_bar = "▓" * mini_bar_len + "░" * (15 - mini_bar_len)
        table.add_row(
            category,
            str(score),
            str(max_pts_cat),
            f"[{grade_color}]{grade}[/{grade_color}]",
            f"[{grade_color}]{mini_bar}[/{grade_color}]",
        )

    console.print(table)

    # Raw stats
    console.print(f"\n[bold]Project Stats:[/bold]")
    console.print(f"  Source files: [cyan]{stats['total_source_files']}[/cyan]  "
                  f"Test files: [cyan]{stats['test_files']}[/cyan]  "
                  f"Total lines: [cyan]{stats['total_lines']:,}[/cyan]")
    console.print(f"  Functions: [cyan]{stats['total_functions']}[/cyan]  "
                  f"Documented: [cyan]{stats['documented_functions']}[/cyan]  "
                  f"Open TODOs: [cyan]{stats['total_todos']}[/cyan]")

    # Recommendations
    console.print(f"\n[bold yellow]💡 Top Recommendations:[/bold yellow]")
    recs = []
    if breakdown["Documentation Coverage"] < 1000:
        recs.append("Add docstrings to your functions — even one-liners help AI understand your code.")
    if breakdown["TODO Density"] < 1000:
        recs.append("Resolve TODOs/FIXMEs before your next AI session — they confuse context.")
    if breakdown["Test Coverage"] < 750:
        recs.append("Add test files — a 20% test ratio earns full points.")
    if breakdown["Import Health"] < 1000:
        recs.append("Fix broken/circular imports — they're a common regression source.")
    if not recs:
        recs.append("Your project is in great shape! Run `vibeguard guard` before big changes.")
    for rec in recs[:3]:
        console.print(f"  [dim]→[/dim] {rec}")
