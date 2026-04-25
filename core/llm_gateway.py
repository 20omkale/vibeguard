"""
VibeGuard — Dual-Engine LLM Gateway
Routes requests to Premium Cloud APIs (OpenAI) or Free Local Models (Ollama).
"""

import os
from openai import OpenAI
from rich.console import Console

console = Console()

def get_llm_client():
    """
    Returns an configured OpenAI-compatible client and the model name to use.
    Auto-detects API keys. Falls back to Ollama.
    """
    openai_key = os.getenv("OPENAI_API_KEY")
    
    # Engine 1: Premium Cloud Engine
    if openai_key and openai_key != "your_key_here":
        console.print("[dim]🧠 Routing to Premium Cloud Engine (OpenAI)[/dim]")
        return OpenAI(api_key=openai_key), "gpt-4o"
    
    # Engine 2: Free Offline Engine (Ollama)
    console.print("[dim]🆓 No API key detected. Routing to Free Local Engine (Ollama)...[/dim]")
    
    # We use the standard openai library but point it to local Ollama server
    try:
        client = OpenAI(
            base_url="http://localhost:11434/v1",
            api_key="ollama" # required but ignored by Ollama
        )
        return client, "llama3" # You can change this to deepseek-coder if preferred
    except Exception as e:
        console.print(f"[bold red]❌ Failed to connect to local Ollama server.[/bold red]")
        console.print("Please make sure Ollama is installed and running on port 11434.")
        raise e
