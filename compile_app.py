"""
VibeGuard — Executable Compiler
Packages the entire VibeGuard application into a single standalone .exe file.
Hides source code and makes the application distributable to clients.
"""

import os
import subprocess
import sys
import io
from rich.console import Console

# Force UTF-8 output on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if sys.stderr.encoding and sys.stderr.encoding.lower() != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

console = Console()

def run_compiler():
    console.print("\n[bold yellow]📦 VibeGuard Standalone Compiler[/bold yellow]")
    
    # Check if PyInstaller is installed
    try:
        import PyInstaller
    except ImportError:
        console.print("[dim]PyInstaller not found. Installing...[/dim]")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
        
    console.print("[cyan]Starting PyInstaller build...[/cyan]")
    
    # We use --onefile to make it a single executable
    # We use --name VibeGuard to name the output
    # We use --clean to clear previous builds
    command = [
        sys.executable, "-m", "PyInstaller",
        "--name", "VibeGuard",
        "--onefile",
        "--clean",
        "-y",
        "--add-data", "ui;ui",
        "--add-data", "server.py;.",
        "--add-data", "core;core",
        "--hidden-import", "rich",
        "--hidden-import", "click",
        "--hidden-import", "flask",
        "--hidden-import", "flask_cors",
        "--hidden-import", "openai",
        "--hidden-import", "groq",
        "--hidden-import", "google.generativeai",
        "--hidden-import", "anthropic",
        "--hidden-import", "httpx",
        "--hidden-import", "core.config_manager",
        "--hidden-import", "core.llm_gateway",
        "--hidden-import", "core.autonomous_agent",
        "--hidden-import", "core.project_genesis",
        "--hidden-import", "core.session_protector",
        "--hidden-import", "core.error_detective",
        "--hidden-import", "core.initializer",
        "--hidden-import", "core.memory_engine",
        "--hidden-import", "core.change_guardian",
        "--hidden-import", "core.context_compressor",
        "--hidden-import", "core.regression_tracker",
        "--hidden-import", "core.telemetry",
        # Aggressive Compiler Pruning (Senior Dev Hack for lightning fast boot)
        "--exclude-module", "pandas",
        "--exclude-module", "numpy",
        "--exclude-module", "torch",
        "--exclude-module", "scipy",
        "--exclude-module", "matplotlib",
        "--exclude-module", "tensorboard",
        "--exclude-module", "PyQt5",
        "--exclude-module", "PyQt6",
        "--exclude-module", "IPython",
        "--exclude-module", "notebook",
        "--exclude-module", "boto3",
        "--exclude-module", "botocore",
        "vibeguard.py"
    ]
    
    try:
        subprocess.check_call(command)
        console.print("\n[bold green]✅ Compilation Successful![/bold green]")
        console.print("Your standalone application is located at: [cyan]dist/VibeGuard.exe[/cyan]")
        console.print("You can safely send this single file to clients. They do not need Python installed.")
    except subprocess.CalledProcessError as e:
        console.print(f"\n[bold red]❌ Compilation failed: {e}[/bold red]")

if __name__ == "__main__":
    run_compiler()
