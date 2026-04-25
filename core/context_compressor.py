"""
VibeGuard — Context Compressor
Reduces codebase token count by up to 70% for AI context windows.
"""

import os
import re
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel
from rich.table import Table

console = Console()

IGNORE_DIRS = {"node_modules", "__pycache__", ".git", "dist", "build", ".next", "venv", ".venv"}

COMPRESSIBLE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs",
    ".java", ".cpp", ".c", ".h", ".cs", ".rb",
}


# ─── Token estimation ─────────────────────────────────────────────────────────

def _estimate_tokens(text: str) -> int:
    """Rough token count: ~4 chars per token (GPT/Claude heuristic)."""
    return max(1, len(text) // 4)


# ─── Compression strategies ───────────────────────────────────────────────────

def _strip_python_comments(source: str) -> str:
    """Remove Python single-line comments and docstrings."""
    # Remove inline comments (but not # inside strings)
    lines = []
    for line in source.splitlines():
        # Strip trailing comment
        stripped = re.sub(r'\s+#[^\'\"]*$', '', line.rstrip())
        lines.append(stripped)
    source = "\n".join(lines)
    # Remove triple-quoted docstrings (simple heuristic)
    source = re.sub(r'"""[\s\S]*?"""', '""""""', source)
    source = re.sub(r"'''[\s\S]*?'''", "''''''", source)
    return source


def _strip_js_comments(source: str) -> str:
    """Remove JS/TS single-line and block comments."""
    # Block comments
    source = re.sub(r'/\*[\s\S]*?\*/', '', source)
    # Single-line comments (not inside strings — approximate)
    source = re.sub(r'(?<!:)//.*', '', source)
    return source


def _collapse_blank_lines(source: str) -> str:
    """Collapse 3+ consecutive blank lines into 1."""
    return re.sub(r'\n{3,}', '\n\n', source)


def _shorten_long_strings(source: str) -> str:
    """Truncate very long string literals (e.g. base64 embeds)."""
    # Match strings longer than 200 chars
    def truncate_match(m):
        s = m.group(0)
        if len(s) > 200:
            return s[:100] + "...[TRUNCATED]" + s[-3:]
        return s

    source = re.sub(r'"[^"]{200,}"', truncate_match, source)
    source = re.sub(r"'[^']{200,}'", truncate_match, source)
    return source


def compress_file(path: Path) -> tuple[str, int, int]:
    """
    Compress a single file.
    Returns: (compressed_content, original_tokens, compressed_tokens)
    """
    try:
        original = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return "", 0, 0

    original_tokens = _estimate_tokens(original)
    compressed = original
    ext = path.suffix.lower()

    if ext == ".py":
        compressed = _strip_python_comments(compressed)
    elif ext in (".js", ".ts", ".jsx", ".tsx"):
        compressed = _strip_js_comments(compressed)

    compressed = _collapse_blank_lines(compressed)
    compressed = _shorten_long_strings(compressed)

    compressed_tokens = _estimate_tokens(compressed)
    return compressed, original_tokens, compressed_tokens


def run_compress(target_dir: Optional[str] = None, output_file: Optional[str] = None) -> None:
    """
    Compress the entire codebase into a single AI-friendly context file.
    """
    root = Path(target_dir) if target_dir else Path.cwd()
    out_path = Path(output_file) if output_file else root / "COMPRESSED_CONTEXT.txt"

    console.print(f"\n[bold cyan]🗜️  VibeGuard Context Compressor[/bold cyan]")
    console.print(f"[dim]Target: {root}[/dim]\n")

    results = []
    all_compressed_parts = []
    total_original = 0
    total_compressed = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}[/bold cyan]"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Compressing...", total=None)

        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not d.startswith(".")]
            for fname in filenames:
                fpath = Path(dirpath) / fname
                if fpath.suffix.lower() not in COMPRESSIBLE_EXTENSIONS:
                    continue
                rel = str(fpath.relative_to(root))
                progress.update(task, description=f"Compressing {rel[:50]}")

                compressed, orig_tok, comp_tok = compress_file(fpath)
                if not compressed.strip():
                    continue

                results.append({
                    "file": rel,
                    "original_tokens": orig_tok,
                    "compressed_tokens": comp_tok,
                    "savings_pct": round(100 * (1 - comp_tok / max(orig_tok, 1)), 1),
                })
                total_original += orig_tok
                total_compressed += comp_tok

                all_compressed_parts.append(f"// ── FILE: {rel} ──\n{compressed.strip()}\n")

    # Write output
    header = (
        "# VibeGuard Compressed Context\n"
        f"# Generated from: {root}\n"
        f"# Original tokens (est.): {total_original:,}\n"
        f"# Compressed tokens (est.): {total_compressed:,}\n"
        f"# Savings: {round(100*(1-total_compressed/max(total_original,1)),1)}%\n\n"
    )
    out_path.write_text(header + "\n\n".join(all_compressed_parts), encoding="utf-8")

    # Print summary table
    savings_pct = round(100 * (1 - total_compressed / max(total_original, 1)), 1)

    console.print(f"[bold green]✅ Compression complete![/bold green]")
    console.print()

    summary = Table(show_header=True, header_style="bold cyan", box=None, padding=(0, 2))
    summary.add_column("Metric")
    summary.add_column("Value", justify="right")
    summary.add_row("Files processed", str(len(results)))
    summary.add_row("Original tokens (est.)", f"{total_original:,}")
    summary.add_row("Compressed tokens (est.)", f"{total_compressed:,}")
    summary.add_row("[bold green]Token savings[/bold green]", f"[bold green]{savings_pct}%[/bold green]")
    summary.add_row("Output file", str(out_path))
    console.print(summary)

    # Top savings files
    if results:
        console.print(f"\n[bold]Top compression wins:[/bold]")
        top = sorted(results, key=lambda x: x["savings_pct"], reverse=True)[:5]
        for r in top:
            console.print(f"  [dim]→[/dim] [cyan]{r['file']}[/cyan]  "
                          f"[green]{r['savings_pct']}% saved[/green]  "
                          f"([dim]{r['original_tokens']}→{r['compressed_tokens']} tokens[/dim])")

    console.print(f"\n[dim]💡 Paste [bold]{out_path.name}[/bold] at the start of your AI session.[/dim]")
