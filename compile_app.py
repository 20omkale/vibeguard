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
        "--hidden-import", "rich",
        "--hidden-import", "click",
        "--hidden-import", "openai",
        # Aggressive Compiler Pruning (Senior Dev Hack for lightning fast boot)
        "--exclude-module", "pandas",
        "--exclude-module", "numpy",
        "--exclude-module", "torch",
        "--exclude-module", "scipy",
        "--exclude-module", "matplotlib",
        "--exclude-module", "tensorboard",
        "--exclude-module", "tkinter",
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
