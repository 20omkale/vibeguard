"""
VibeGuard — Memory Engine
Scans the codebase and maintains PROJECT_MEMORY.md as a persistent truth source.
"""

import os
import ast
import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

console = Console()

IGNORE_DIRS = {
    "node_modules", "__pycache__", ".git", "dist", "build",
    ".next", "venv", ".venv", "env", ".env", "coverage",
    ".pytest_cache", ".mypy_cache", "target", "out", ".cache",
}

SUPPORTED_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java",
    ".cpp", ".c", ".h", ".cs", ".rb", ".php", ".swift", ".kt",
    ".vue", ".svelte", ".html", ".css", ".scss", ".json", ".yaml", ".yml",
}


def _hash_file(path: Path) -> str:
    """Quick MD5 hash of file contents."""
    try:
        return hashlib.md5(path.read_bytes()).hexdigest()[:8]
    except Exception:
        return "unknown"


def _parse_python_symbols(path: Path) -> dict:
    """Extract functions, classes, and imports from a Python file."""
    symbols = {"functions": [], "classes": [], "imports": [], "todos": []}
    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                doc = ast.get_docstring(node) or ""
                symbols["functions"].append({
                    "name": node.name,
                    "line": node.lineno,
                    "doc": doc[:80] if doc else None,
                    "args": [a.arg for a in node.args.args],
                })
            elif isinstance(node, ast.AsyncFunctionDef):
                doc = ast.get_docstring(node) or ""
                symbols["functions"].append({
                    "name": f"async {node.name}",
                    "line": node.lineno,
                    "doc": doc[:80] if doc else None,
                    "args": [a.arg for a in node.args.args],
                })
            elif isinstance(node, ast.ClassDef):
                doc = ast.get_docstring(node) or ""
                methods = [
                    n.name for n in ast.walk(node)
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n != node
                ]
                symbols["classes"].append({
                    "name": node.name,
                    "line": node.lineno,
                    "doc": doc[:80] if doc else None,
                    "methods": methods[:10],
                })
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    symbols["imports"].append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    symbols["imports"].append(node.module)

        # Extract TODOs from comments
        for i, line in enumerate(source.splitlines(), 1):
            stripped = line.strip()
            if any(tag in stripped.upper() for tag in ("TODO", "FIXME", "HACK", "XXX", "BUG")):
                symbols["todos"].append({"line": i, "text": stripped[:120]})

    except SyntaxError:
        symbols["parse_error"] = True
    except Exception as e:
        symbols["parse_error"] = str(e)

    return symbols


def _parse_js_symbols(path: Path) -> dict:
    """Basic symbol extraction for JS/TS files."""
    symbols = {"functions": [], "classes": [], "imports": [], "todos": []}
    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
        lines = source.splitlines()
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            # Functions
            if stripped.startswith(("function ", "const ", "let ", "export function", "export const", "export default function")):
                if "=>" in line or "function" in line:
                    name_part = stripped.split("(")[0].split(" ")[-1].strip("=").strip()
                    if name_part and not name_part.startswith("//"):
                        symbols["functions"].append({"name": name_part, "line": i})
            # Classes
            if stripped.startswith(("class ", "export class")):
                name_part = stripped.split(" ")[1].split("{")[0].split("(")[0].strip()
                symbols["classes"].append({"name": name_part, "line": i})
            # Imports
            if stripped.startswith(("import ", "require(")):
                symbols["imports"].append(stripped[:100])
            # TODOs
            if any(tag in stripped.upper() for tag in ("TODO", "FIXME", "HACK", "XXX")):
                symbols["todos"].append({"line": i, "text": stripped[:120]})
    except Exception:
        pass
    return symbols


def scan_codebase(root: Path) -> dict:
    """
    Walk the entire codebase and return a structured memory map.
    Returns a dict with: files, stats, todos, structure.
    """
    memory = {
        "scanned_at": datetime.now().isoformat(),
        "root": str(root),
        "files": {},
        "stats": {
            "total_files": 0,
            "total_lines": 0,
            "total_todos": 0,
            "by_extension": {},
        },
        "todos": [],
        "entry_points": [],
    }

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]Scanning codebase...[/bold cyan]"),
        BarColumn(),
        TextColumn("[dim]{task.description}[/dim]"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("", total=None)

        for dirpath, dirnames, filenames in os.walk(root):
            # Prune ignored directories
            dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not d.startswith(".")]

            for filename in filenames:
                fpath = Path(dirpath) / filename
                ext = fpath.suffix.lower()

                if ext not in SUPPORTED_EXTENSIONS:
                    continue

                rel_path = str(fpath.relative_to(root))
                progress.update(task, description=rel_path[:60])

                try:
                    content = fpath.read_text(encoding="utf-8", errors="ignore")
                    lines = content.splitlines()
                    line_count = len(lines)
                except Exception:
                    continue

                file_info = {
                    "path": rel_path,
                    "extension": ext,
                    "lines": line_count,
                    "hash": _hash_file(fpath),
                    "size_bytes": fpath.stat().st_size,
                }

                # Symbol extraction
                if ext == ".py":
                    file_info["symbols"] = _parse_python_symbols(fpath)
                elif ext in (".js", ".ts", ".jsx", ".tsx"):
                    file_info["symbols"] = _parse_js_symbols(fpath)

                # Collect TODOs globally
                if "symbols" in file_info and file_info["symbols"].get("todos"):
                    for todo in file_info["symbols"]["todos"]:
                        memory["todos"].append({**todo, "file": rel_path})

                # Detect entry points
                fname_lower = filename.lower()
                if fname_lower in ("main.py", "app.py", "index.py", "server.py", "index.js",
                                   "main.js", "app.js", "index.ts", "main.ts", "app.ts",
                                   "index.jsx", "index.tsx", "main.go", "main.rs"):
                    memory["entry_points"].append(rel_path)

                memory["files"][rel_path] = file_info
                memory["stats"]["total_files"] += 1
                memory["stats"]["total_lines"] += line_count
                memory["stats"]["total_todos"] += len(file_info.get("symbols", {}).get("todos", []))
                memory["stats"]["by_extension"][ext] = memory["stats"]["by_extension"].get(ext, 0) + 1

    return memory


def generate_memory_doc(memory: dict, output_path: Path) -> None:
    """Write the PROJECT_MEMORY.md file from the scanned memory map."""
    stats = memory["stats"]
    scanned_at = memory["scanned_at"]

    lines = [
        "# 🧠 PROJECT_MEMORY.md",
        "> Auto-generated by **VibeGuard** — do not edit manually.",
        f"> Last scan: `{scanned_at}`",
        "",
        "---",
        "",
        "## 📊 Project Stats",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total Files | {stats['total_files']} |",
        f"| Total Lines | {stats['total_lines']:,} |",
        f"| Open TODOs | {stats['total_todos']} |",
        f"| Entry Points | {len(memory['entry_points'])} |",
        "",
    ]

    # Language breakdown
    if stats["by_extension"]:
        lines += ["## 🗂️ Language Breakdown", ""]
        sorted_exts = sorted(stats["by_extension"].items(), key=lambda x: x[1], reverse=True)
        lines.append("| Extension | Files |")
        lines.append("|-----------|-------|")
        for ext, count in sorted_exts[:15]:
            lines.append(f"| `{ext}` | {count} |")
        lines.append("")

    # Entry points
    if memory["entry_points"]:
        lines += ["## 🚀 Entry Points", ""]
        for ep in memory["entry_points"]:
            lines.append(f"- `{ep}`")
        lines.append("")

    # Key files (by line count, top 20)
    lines += ["## 📁 Key Files", ""]
    sorted_files = sorted(memory["files"].values(), key=lambda x: x["lines"], reverse=True)[:20]
    lines.append("| File | Lines | Extension |")
    lines.append("|------|-------|-----------|")
    for f in sorted_files:
        lines.append(f"| `{f['path']}` | {f['lines']} | `{f['extension']}` |")
    lines.append("")

    # Functions & Classes (Python/JS)
    all_functions = []
    all_classes = []
    for rel_path, fdata in memory["files"].items():
        syms = fdata.get("symbols", {})
        for fn in syms.get("functions", []):
            all_functions.append({**fn, "file": rel_path})
        for cls in syms.get("classes", []):
            all_classes.append({**cls, "file": rel_path})

    if all_classes:
        lines += ["## 🏛️ Classes", ""]
        for cls in all_classes[:30]:
            doc_str = f" — {cls['doc']}" if cls.get("doc") else ""
            lines.append(f"- **`{cls['name']}`** (`{cls['file']}` L{cls['line']}){doc_str}")
            if cls.get("methods"):
                lines.append(f"  - Methods: {', '.join(f'`{m}`' for m in cls['methods'][:8])}")
        lines.append("")

    if all_functions:
        lines += ["## ⚙️ Functions", ""]
        for fn in all_functions[:50]:
            args_str = ", ".join(fn.get("args", [])[:5]) if fn.get("args") else ""
            doc_str = f" — {fn['doc']}" if fn.get("doc") else ""
            lines.append(f"- **`{fn['name']}({args_str})`** (`{fn['file']}` L{fn['line']}){doc_str}")
        lines.append("")

    # TODOs
    if memory["todos"]:
        lines += ["## ⚠️ Open TODOs & Fixmes", ""]
        for todo in memory["todos"][:30]:
            lines.append(f"- `{todo['file']}` L{todo['line']}: `{todo['text']}`")
        if len(memory["todos"]) > 30:
            lines.append(f"- ... and {len(memory['todos']) - 30} more")
        lines.append("")

    lines += [
        "---",
        "",
        "_This file is your AI's ground truth. Paste it at the start of every AI session._",
    ]

    output_path.write_text("\n".join(lines), encoding="utf-8")


def generate_project_memory(target_dir: str) -> str:
    """Returns a text summary of the codebase for LLM context."""
    root = Path(target_dir.strip().strip('"').strip("'"))
    if not root.exists():
        return "Project directory not found."
    
    memory = scan_codebase(root)
    
    summary = [
        f"Project Root: {memory['root']}",
        f"Total Files: {memory['stats']['total_files']}",
        f"Main Languages: {', '.join(memory['stats']['by_extension'].keys())}",
        "\nEntry Points:",
    ]
    summary += [f"- {ep}" for ep in memory["entry_points"]]
    
    summary.append("\nKey Files & Symbols:")
    for rel_path, fdata in list(memory["files"].items())[:15]:
        syms = fdata.get("symbols", {})
        funcs = [f["name"] for f in syms.get("functions", [])[:5]]
        summary.append(f"- {rel_path} ({fdata['lines']} lines): {', '.join(funcs)}")
        
    return "\n".join(summary)


def run_scan(target_dir: Optional[str] = None) -> dict:
    """Main entry point: scan + generate memory doc."""
    root = Path(target_dir) if target_dir else Path.cwd()
    if not root.exists():
        console.print(f"[red]❌ Directory not found: {root}[/red]")
        return {}

    console.print(f"\n[bold cyan]🔍 VibeGuard Memory Engine[/bold cyan]")
    console.print(f"[dim]Scanning: {root}[/dim]\n")

    memory = scan_codebase(root)
    output_path = root / "PROJECT_MEMORY.md"
    generate_memory_doc(memory, output_path)

    stats = memory["stats"]
    console.print(f"\n[bold green]✅ Scan complete![/bold green]")
    console.print(f"   [cyan]Files scanned:[/cyan] {stats['total_files']}")
    console.print(f"   [cyan]Total lines:[/cyan]   {stats['total_lines']:,}")
    console.print(f"   [cyan]Open TODOs:[/cyan]    {stats['total_todos']}")
    console.print(f"   [cyan]Memory saved:[/cyan]  {output_path}")

    return memory
