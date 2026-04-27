"""
VibeGuard — Config Manager & First-Run Wizard
Handles API key storage, provider selection, and first-time setup.
Stores config globally in ~/.vibeguard/config.json — never in project files.
"""

import os
import json
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.text import Text
from rich.rule import Rule

console = Console(force_terminal=True)

CONFIG_DIR = Path.home() / ".vibeguard"
CONFIG_FILE = CONFIG_DIR / "config.json"

PROVIDERS = {
    "groq": {
        "name": "Groq (FREE — No credit card needed!)",
        "desc": "llama3-70b on Groq Cloud. 14,400 free requests/day.",
        "url": "https://console.groq.com (free signup, 30 seconds)",
        "env_key": "GROQ_API_KEY",
        "model": "llama-3.3-70b-versatile",
    },
    "gemini": {
        "name": "Google Gemini (FREE tier available)",
        "desc": "gemini-1.5-flash. Generous free quota.",
        "url": "https://aistudio.google.com (free Google account)",
        "env_key": "GEMINI_API_KEY",
        "model": "gemini-1.5-flash",
    },
    "openai": {
        "name": "OpenAI GPT-4o (Best quality — Paid)",
        "desc": "Most powerful. Requires OpenAI API key with credits.",
        "url": "https://platform.openai.com",
        "env_key": "OPENAI_API_KEY",
        "model": "gpt-4o",
    },
    "anthropic": {
        "name": "Anthropic Claude (Best quality — Paid)",
        "desc": "claude-3-5-sonnet. Requires Anthropic API key.",
        "url": "https://console.anthropic.com",
        "env_key": "ANTHROPIC_API_KEY",
        "model": "claude-3-5-sonnet-20241022",
    },
    "ollama": {
        "name": "Local Ollama (100% Offline — Advanced)",
        "desc": "Requires Ollama installed and llama3 downloaded (~4GB).",
        "url": "https://ollama.com/download",
        "env_key": None,
        "model": "llama3",
    },
}


def load_config() -> dict:
    """Load global VibeGuard config."""
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            # Ensure essential keys exist
            if "api_keys" not in data: data["api_keys"] = {}
            if "ngrok_token" not in data: data["ngrok_token"] = ""
            return data
        except Exception:
            pass
    return {"provider": "groq", "api_keys": {}, "ngrok_token": ""}


def save_config(config: dict):
    """Save global VibeGuard config."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")


def get_active_provider() -> str:
    """Get the currently configured provider name."""
    config = load_config()
    return config.get("provider", "")


def get_api_key_for_provider(provider: str) -> str:
    """Get the API key for the given provider (from config or env)."""
    config = load_config()
    stored = config.get("api_keys", {}).get(provider, "")
    if stored:
        return stored
    # Fallback to environment variables
    env_key = PROVIDERS.get(provider, {}).get("env_key")
    if env_key:
        return os.getenv(env_key, "")
    return ""


def is_configured() -> bool:
    """Check if VibeGuard has been configured with a working provider."""
    config = load_config()
    provider = config.get("provider", "")
    if not provider:
        return False
    if provider == "ollama":
        return True  # Ollama doesn't need an API key in config
    return bool(get_api_key_for_provider(provider))


def run_first_time_wizard():
    """
    Interactive first-time setup wizard.
    Guides the user through provider selection and API key entry.
    """
    console.print()
    console.print(Panel(
        "[bold cyan]Welcome to VibeGuard![/bold cyan]\n\n"
        "I'm your AI-powered development partner.\n"
        "Let's do a [bold]one-time setup[/bold] — takes about 60 seconds.\n\n"
        "[dim]Your config is saved globally and never committed to any project.[/dim]",
        border_style="cyan",
        padding=(1, 3),
    ))

    console.print("\n[bold white]How should VibeGuard power its AI brain?[/bold white]\n")
    console.print("  [bold cyan][1][/bold cyan]  🆓  [bold]Groq FREE[/bold] — llama3-70b, 14,400 requests/day, zero cost")
    console.print("       [dim]→ Get free key at: https://console.groq.com (30 seconds)[/dim]")
    console.print()
    console.print("  [bold cyan][2][/bold cyan]  🆓  [bold]Google Gemini FREE[/bold] — gemini-1.5-flash, generous free quota")
    console.print("       [dim]→ Get free key at: https://aistudio.google.com[/dim]")
    console.print()
    console.print("  [bold cyan][3][/bold cyan]  ⭐  [bold]OpenAI GPT-4o[/bold] — Best quality (requires paid API key)")
    console.print()
    console.print("  [bold cyan][4][/bold cyan]  ⭐  [bold]Anthropic Claude[/bold] — Best quality (requires paid API key)")
    console.print()
    console.print("  [bold cyan][5][/bold cyan]  🔒  [bold]Local Ollama[/bold] — 100% offline, no internet needed")
    console.print("       [dim]→ Requires Ollama installed + llama3 downloaded (~4GB)[/dim]")
    console.print()

    choice = Prompt.ask(
        "\n[bold]Your choice[/bold]",
        choices=["1", "2", "3", "4", "5"],
        default="1"
    )

    provider_map = {"1": "groq", "2": "gemini", "3": "openai", "4": "anthropic", "5": "ollama"}
    provider = provider_map[choice]
    pinfo = PROVIDERS[provider]

    config = load_config()
    config["provider"] = provider

    if provider == "ollama":
        console.print(f"\n[green]✓ Selected: Local Ollama[/green]")
        console.print("[dim]Make sure Ollama is running: `ollama serve` and llama3 is downloaded.[/dim]")
        save_config(config)
        console.print("\n[bold green]✅ VibeGuard configured![/bold green] You're ready to build.")
        return

    # API key entry
    console.print(f"\n[green]✓ Selected: {pinfo['name']}[/green]")
    console.print(f"\n[dim]To get your free API key, go to: {pinfo['url']}[/dim]")
    console.print("[dim]It only takes about 30 seconds. Copy the key and paste it below.[/dim]\n")

    # Check if already in environment
    env_key_name = pinfo["env_key"]
    existing_env = os.getenv(env_key_name, "")
    if existing_env and existing_env != "your_key_here":
        console.print(f"[green]✓ Found {env_key_name} in environment variables.[/green]")
        use_env = Confirm.ask("Use this key?", default=True)
        if use_env:
            console.print("[bold green]✅ VibeGuard configured![/bold green] You're ready to build.")
            save_config(config)
            return

    api_key = Prompt.ask(f"\nPaste your [bold]{env_key_name}[/bold] here", password=True)
    api_key = api_key.strip()

    if not api_key:
        console.print("[yellow]⚠️  No key entered. You can run `vibeguard config` anytime to set this up.[/yellow]")
        return

    # Validate the key
    console.print(f"\n[cyan]🔍 Validating your {provider} API key...[/cyan]")
    valid, error_msg = _validate_key(provider, api_key, pinfo["model"])

    if valid:
        if "api_keys" not in config:
            config["api_keys"] = {}
        config["api_keys"][provider] = api_key
        save_config(config)
        console.print(f"\n[bold green]✅ Key validated and saved![/bold green]")
        console.print("[bold green]VibeGuard is ready to build. Let's go! 🚀[/bold green]")
    else:
        console.print(f"\n[red]❌ Key validation failed: {error_msg}[/red]")
        console.print("[dim]You can retry with `vibeguard config` anytime.[/dim]")


def _validate_key(provider: str, api_key: str, model: str) -> tuple[bool, str]:
    """Quick validation ping to the provider's API."""
    try:
        if provider == "groq":
            from groq import Groq
            client = Groq(api_key=api_key)
            client.chat.completions.create(
                messages=[{"role": "user", "content": "hi"}],
                model=model,
                max_tokens=5,
            )
            return True, ""
        elif provider == "gemini":
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            model_obj = genai.GenerativeModel("gemini-1.5-flash")
            model_obj.generate_content("hi")
            return True, ""
        elif provider == "openai":
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            client.chat.completions.create(
                messages=[{"role": "user", "content": "hi"}],
                model="gpt-4o-mini",
                max_tokens=5,
            )
            return True, ""
        elif provider == "anthropic":
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=5,
                messages=[{"role": "user", "content": "hi"}],
            )
            return True, ""
    except Exception as e:
        return False, str(e)[:200]
    return False, "Unknown error"


def run_config_command():
    """Entry point for `vibeguard config` command."""
    console.print("\n[bold cyan]VibeGuard Configuration[/bold cyan]\n")
    
    config = load_config()
    current = config.get("provider", "not set")
    console.print(f"  [dim]Current provider:[/dim] [yellow]{current}[/yellow]")
    if current != "not set" and current != "ollama":
        key = get_api_key_for_provider(current)
        masked = f"{key[:8]}...{key[-4:]}" if len(key) > 12 else "***"
        console.print(f"  [dim]API key:[/dim] [yellow]{masked if key else 'not set'}[/yellow]")
    console.print()
    
    run_first_time_wizard()
