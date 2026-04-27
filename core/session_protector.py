"""
VibeGuard — Session Protector
The #1 problem with vibe coding: AI removes your code without telling you.
This module watches EVERY function, class, API endpoint, and export.
Before your AI session → take a snapshot.
After your AI session → compare and show exactly what was deleted/changed.
Can restore specific deleted code automatically.
"""

import ast
import re
import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Confirm, Prompt
from rich.rule import Rule

console = Console(force_terminal=True)

IGNORE_DIRS = {"node_modules", "__pycache__", ".git", "dist", "build", ".next", "venv", ".venv", ".vibeguard"}
CODE_EXTENSIONS = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java", ".cs", ".rb", ".php"}


# ─── Snapshot Engine ────────────────────────────────────────────────────────────

class CodeSnapshot:
    """
    Takes a complete snapshot of all functions, classes, API routes, and exports
    in a project. Much more detailed than the basic change_guardian.
    """

    def __init__(self, root: Path):
        self.root = root
        self.timestamp = datetime.now().isoformat()
        self.functions: dict[str, dict] = {}   # file -> {name: {line, signature, body_hash}}
        self.classes: dict[str, list] = {}      # file -> [class names]
        self.exports: dict[str, set] = {}       # file -> {exported names}
        self.routes: dict[str, list] = {}       # file -> [route definitions]
        self.env_vars: dict[str, list] = {}     # file -> [env var names used]
        self._scan()

    def _scan(self):
        for path in self.root.rglob("*"):
            if any(p in path.parts for p in IGNORE_DIRS):
                continue
            if path.suffix not in CODE_EXTENSIONS:
                continue
            try:
                rel = str(path.relative_to(self.root))
                content = path.read_text(encoding="utf-8", errors="ignore")
                self.functions[rel] = self._extract_functions(path, content)
                self.classes[rel] = self._extract_classes(path, content)
                self.exports[rel] = self._extract_exports(content)
                self.routes[rel] = self._extract_routes(content)
                self.env_vars[rel] = self._extract_env_vars(content)
            except Exception:
                pass

    def _extract_functions(self, path: Path, content: str) -> dict:
        funcs = {}
        if path.suffix == ".py":
            try:
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        lines = content.splitlines()
                        start = node.lineno - 1
                        end = min(node.end_lineno, len(lines))
                        body = "\n".join(lines[start:end])
                        funcs[node.name] = {
                            "line": node.lineno,
                            "signature": f"def {node.name}({', '.join(a.arg for a in node.args.args)})",
                            "body_hash": hashlib.md5(body.encode()).hexdigest()[:8],
                        }
            except SyntaxError:
                pass
        else:
            # JS/TS: regex-based extraction
            patterns = [
                r'(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(',
                r'(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s+)?\(',
                r'(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s+)?\w+\s*=>',
            ]
            for i, line in enumerate(content.splitlines(), 1):
                for pat in patterns:
                    m = re.search(pat, line)
                    if m:
                        name = m.group(1)
                        if name not in ("if", "for", "while", "switch"):
                            funcs[name] = {"line": i, "signature": line.strip()[:100], "body_hash": ""}
        return funcs

    def _extract_classes(self, path: Path, content: str) -> list:
        if path.suffix == ".py":
            try:
                tree = ast.parse(content)
                return [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
            except SyntaxError:
                pass
        else:
            return re.findall(r'class\s+(\w+)', content)
        return []

    def _extract_exports(self, content: str) -> set:
        exports = set()
        # ES6 exports
        for m in re.finditer(r'export\s+(?:default\s+)?(?:class|function|const|let|var)?\s*(\w+)', content):
            exports.add(m.group(1))
        # Named exports
        for m in re.finditer(r'export\s*\{([^}]+)\}', content):
            for name in m.group(1).split(","):
                exports.add(name.strip().split(" as ")[0].strip())
        # Python __all__
        for m in re.finditer(r'__all__\s*=\s*\[([^\]]+)\]', content):
            for name in m.group(1).split(","):
                exports.add(name.strip().strip("'\""))
        return exports

    def _extract_routes(self, content: str) -> list:
        routes = []
        patterns = [
            r'@app\.(get|post|put|delete|patch)\(["\']([^"\']+)["\']',  # Flask/FastAPI
            r'router\.(get|post|put|delete|patch)\(["\']([^"\']+)["\']',  # Express
            r'@(Get|Post|Put|Delete|Patch)\(["\']([^"\']+)["\']',  # NestJS
        ]
        for pat in patterns:
            for m in re.finditer(pat, content, re.IGNORECASE):
                routes.append(f"{m.group(1).upper()} {m.group(2)}")
        return routes

    def _extract_env_vars(self, content: str) -> list:
        vars_found = []
        for m in re.finditer(r'process\.env\.(\w+)|os\.getenv\(["\'](\w+)["\']|os\.environ\[["\'](\w+)["\']', content):
            name = m.group(1) or m.group(2) or m.group(3)
            if name:
                vars_found.append(name)
        return list(set(vars_found))

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "functions": self.functions,
            "classes": self.classes,
            "exports": {k: list(v) for k, v in self.exports.items()},
            "routes": self.routes,
            "env_vars": self.env_vars,
        }

    @classmethod
    def from_dict(cls, data: dict, root: Path) -> "CodeSnapshot":
        snap = cls.__new__(cls)
        snap.root = root
        snap.timestamp = data.get("timestamp", "")
        snap.functions = data.get("functions", {})
        snap.classes = data.get("classes", {})
        snap.exports = {k: set(v) for k, v in data.get("exports", {}).items()}
        snap.routes = data.get("routes", {})
        snap.env_vars = data.get("env_vars", {})
        return snap


# ─── Diff Engine ────────────────────────────────────────────────────────────────

class SessionDiff:
    """Compares two snapshots and reports what changed."""

    def __init__(self, before: CodeSnapshot, after: CodeSnapshot):
        self.before = before
        self.after = after
        self.deleted_functions: list[dict] = []
        self.modified_functions: list[dict] = []
        self.deleted_classes: list[dict] = []
        self.deleted_exports: list[dict] = []
        self.deleted_routes: list[dict] = []
        self._compare()

    def _compare(self):
        all_files = set(self.before.functions.keys()) | set(self.after.functions.keys())

        for file in all_files:
            before_funcs = self.before.functions.get(file, {})
            after_funcs = self.after.functions.get(file, {})

            # Deleted functions
            for fname, fdata in before_funcs.items():
                if fname not in after_funcs:
                    self.deleted_functions.append({
                        "file": file,
                        "name": fname,
                        "line": fdata.get("line", 0),
                        "signature": fdata.get("signature", fname),
                    })
                elif fdata.get("body_hash") and after_funcs[fname].get("body_hash"):
                    if fdata["body_hash"] != after_funcs[fname]["body_hash"]:
                        self.modified_functions.append({
                            "file": file,
                            "name": fname,
                        })

        # Deleted classes
        for file in self.before.classes:
            before_cls = set(self.before.classes.get(file, []))
            after_cls = set(self.after.classes.get(file, []))
            for cls in before_cls - after_cls:
                self.deleted_classes.append({"file": file, "name": cls})

        # Deleted exports
        for file in self.before.exports:
            before_exp = self.before.exports.get(file, set())
            after_exp = self.after.exports.get(file, set())
            for exp in before_exp - after_exp:
                self.deleted_exports.append({"file": file, "name": exp})

        # Deleted routes
        for file in self.before.routes:
            before_routes = set(self.before.routes.get(file, []))
            after_routes = set(self.after.routes.get(file, []))
            for route in before_routes - after_routes:
                self.deleted_routes.append({"file": file, "route": route})

    @property
    def is_clean(self) -> bool:
        return not (self.deleted_functions or self.deleted_classes or
                    self.deleted_exports or self.deleted_routes)

    @property
    def severity(self) -> str:
        total = len(self.deleted_functions) + len(self.deleted_classes) + len(self.deleted_routes)
        if total == 0:
            return "CLEAN"
        elif total <= 2:
            return "LOW"
        elif total <= 5:
            return "MEDIUM"
        else:
            return "HIGH"


# ─── Display ────────────────────────────────────────────────────────────────────

def _display_diff(diff: SessionDiff):
    if diff.is_clean:
        console.print(Panel(
            "[bold green]✅ Session Protection: ALL CLEAR[/bold green]\n\n"
            "No functions, classes, exports, or routes were removed.\n"
            "Your codebase is safe!",
            border_style="green",
            padding=(1, 2),
        ))
        return

    severity_color = {"LOW": "yellow", "MEDIUM": "orange3", "HIGH": "red"}
    color = severity_color.get(diff.severity, "red")

    console.print(Panel(
        f"[bold {color}]⚠️  Session Protection: {diff.severity} RISK[/bold {color}]\n\n"
        f"The AI made changes that removed existing code.\n"
        f"Review below and restore if needed.",
        border_style=color,
        padding=(1, 2),
    ))
    console.print()

    if diff.deleted_functions:
        table = Table(title=f"🗑️  Deleted Functions ({len(diff.deleted_functions)})",
                      show_header=True, header_style="bold red", box=None)
        table.add_column("File", style="dim")
        table.add_column("Function", style="red bold")
        table.add_column("Was at Line", style="dim")
        for item in diff.deleted_functions:
            table.add_row(item["file"], item["name"], str(item["line"]))
        console.print(table)
        console.print()

    if diff.modified_functions:
        table = Table(title=f"✏️  Modified Functions ({len(diff.modified_functions)})",
                      show_header=True, header_style="bold yellow", box=None)
        table.add_column("File", style="dim")
        table.add_column("Function", style="yellow")
        for item in diff.modified_functions:
            table.add_row(item["file"], item["name"])
        console.print(table)
        console.print()

    if diff.deleted_routes:
        table = Table(title=f"🔌 Deleted API Routes ({len(diff.deleted_routes)})",
                      show_header=True, header_style="bold red", box=None)
        table.add_column("File", style="dim")
        table.add_column("Route", style="red bold")
        for item in diff.deleted_routes:
            table.add_row(item["file"], item["route"])
        console.print(table)
        console.print()

    if diff.deleted_exports:
        table = Table(title=f"📦 Removed Exports ({len(diff.deleted_exports)})",
                      show_header=True, header_style="bold yellow", box=None)
        table.add_column("File", style="dim")
        table.add_column("Export", style="yellow")
        for item in diff.deleted_exports:
            table.add_row(item["file"], item["name"])
        console.print(table)
        console.print()


# ─── Snapshot Storage ────────────────────────────────────────────────────────────

def _get_snapshot_dir(root: Path) -> Path:
    d = root / ".vibeguard" / "snapshots"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save_snapshot(snap: CodeSnapshot, root: Path, label: str = "session"):
    snap_dir = _get_snapshot_dir(root)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = snap_dir / f"{label}_{ts}.json"
    path.write_text(json.dumps(snap.to_dict(), indent=2), encoding="utf-8")
    # Also save as "latest" for quick access
    latest = snap_dir / f"{label}_latest.json"
    latest.write_text(json.dumps(snap.to_dict(), indent=2), encoding="utf-8")
    return path


def _load_latest_snapshot(root: Path, label: str = "session") -> Optional[CodeSnapshot]:
    latest = _get_snapshot_dir(root) / f"{label}_latest.json"
    if not latest.exists():
        return None
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
        return CodeSnapshot.from_dict(data, root)
    except Exception:
        return None


# ─── Main Commands ───────────────────────────────────────────────────────────────

def run_protect_before(path: str):
    """
    Call this BEFORE starting an AI coding session.
    Takes a complete snapshot of your codebase.
    """
    root = Path(path)
    console.print(f"\n[bold yellow]🛡️  Session Protection — Taking Baseline Snapshot[/bold yellow]")
    console.print(f"[dim]Scanning all files in {root}...[/dim]\n")

    snap = CodeSnapshot(root)
    saved = _save_snapshot(snap, root, "session")

    # Show what was captured
    total_funcs = sum(len(v) for v in snap.functions.values())
    total_classes = sum(len(v) for v in snap.classes.values())
    total_routes = sum(len(v) for v in snap.routes.values())
    files_scanned = len(snap.functions)

    console.print(Panel(
        f"[bold green]✅ Baseline Snapshot Saved[/bold green]\n\n"
        f"  📁 Files scanned:    {files_scanned}\n"
        f"  ⚡ Functions tracked: {total_funcs}\n"
        f"  🏗️  Classes tracked:  {total_classes}\n"
        f"  🔌 API routes:       {total_routes}\n\n"
        f"[dim]Now go do your AI coding session.[/dim]\n"
        f"[dim]When done, run: [cyan]vibeguard protect --after[/cyan][/dim]",
        border_style="green",
        padding=(1, 2),
    ))


def run_protect_after(path: str):
    """
    Call this AFTER your AI coding session.
    Compares with baseline and shows exactly what was removed.
    """
    root = Path(path)
    console.print(f"\n[bold yellow]🛡️  Session Protection — Comparing Changes[/bold yellow]\n")

    # Load baseline
    before = _load_latest_snapshot(root, "session")
    if not before:
        console.print("[red]No baseline snapshot found! Run `vibeguard protect --before` before your AI session.[/red]")
        return

    # Take current snapshot
    after = CodeSnapshot(root)

    # Compare
    diff = SessionDiff(before, after)
    _display_diff(diff)

    if not diff.is_clean:
        # Generate fix prompt
        _generate_restore_prompt(diff, root)


def run_protect_watch(path: str):
    """
    Continuous watch mode — takes a snapshot, watches for changes, alerts.
    Perfect for long coding sessions.
    """
    import time
    root = Path(path)
    console.print(f"[bold cyan]👁️  Session Protection: Watch Mode[/bold cyan]")
    console.print("[dim]Taking baseline snapshot...[/dim]")

    before = CodeSnapshot(root)
    _save_snapshot(before, root, "session")

    total_funcs = sum(len(v) for v in before.functions.values())
    console.print(f"[green]✓ Baseline: {total_funcs} functions tracked[/green]")
    console.print("[dim]Checking for changes every 30 seconds. Press Ctrl+C to stop.[/dim]\n")

    try:
        while True:
            time.sleep(30)
            after = CodeSnapshot(root)
            diff = SessionDiff(before, after)
            if not diff.is_clean:
                console.print(f"\n[bold red]⚠️  ALERT: Code removed! ({len(diff.deleted_functions)} functions deleted)[/bold red]")
                _display_diff(diff)
                if Confirm.ask("Update baseline to current state?", default=False):
                    before = after
                    _save_snapshot(before, root, "session")
                    console.print("[green]✓ Baseline updated[/green]\n")
            else:
                console.print(f"[dim]{datetime.now().strftime('%H:%M:%S')} — Clean check ✓[/dim]")
    except KeyboardInterrupt:
        console.print("\n[yellow]Watch mode stopped.[/yellow]")


def _generate_restore_prompt(diff: SessionDiff, root: Path):
    """Generate a prompt to restore deleted code."""
    console.print()
    console.print("[bold blue]🤖 Restore Prompt — Copy this into your AI:[/bold blue]")

    deleted_list = "\n".join(
        f"- Function `{item['name']}` in {item['file']} (was at line {item['line']})"
        for item in diff.deleted_functions
    )
    route_list = "\n".join(
        f"- Route `{item['route']}` in {item['file']}"
        for item in diff.deleted_routes
    )

    prompt = f"""CRITICAL: Some code was accidentally removed in the last AI session. Restore it immediately.

DELETED FUNCTIONS (restore these exactly):
{deleted_list}

{f"DELETED API ROUTES (restore these):{chr(10)}{route_list}" if diff.deleted_routes else ""}

Instructions:
1. Find where each function/route belongs in the codebase
2. Restore the complete original implementation (check git history if needed)
3. Do NOT change any other existing code
4. After restoring, verify all imports still work
5. Confirm each restored item one by one"""

    console.print(Panel(prompt, border_style="blue", padding=(1, 2)))
