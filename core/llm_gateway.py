import os
import json
from pathlib import Path
from rich.console import Console
from .config_manager import load_config, get_api_key_for_provider, PROVIDERS

console = Console(force_terminal=True)

class LLMClient:
    """Unified wrapper around any LLM provider."""
    def __init__(self, provider: str, api_key: str, model: str):
        self.provider = provider
        self.model = self._resolve_model(provider, model, api_key)
        self._api_key = api_key
        self._client = None
        self._init_client()

    def _resolve_model(self, provider: str, suggested_model: str, api_key: str) -> str:
        """Senior Dev Hack: Resolve the best available model version dynamically."""
        # Fallback map for known decommissioned models
        DEPRECATIONS = {
            "llama3-70b-8192": "llama-3.3-70b-versatile",
            "llama3-8b-8192": "llama-3.1-8b-instant",
            "gpt-4-0613": "gpt-4o",
        }
        return DEPRECATIONS.get(suggested_model, suggested_model)

    def _init_client(self):
        if self.provider in ("openai", "groq", "ollama"):
            from openai import OpenAI
            if self.provider == "groq":
                self._client = OpenAI(api_key=self._api_key, base_url="https://api.groq.com/openai/v1")
            elif self.provider == "ollama":
                self._client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
            else:
                self._client = OpenAI(api_key=self._api_key)
        elif self.provider == "anthropic":
            import anthropic
            self._client = anthropic.Anthropic(api_key=self._api_key)
        elif self.provider == "gemini":
            import google.generativeai as genai
            genai.configure(api_key=self._api_key)
            self._client = genai.GenerativeModel(self.model)

    def chat(self, messages: list, temperature: float = 0.2, max_tokens: int = 4096) -> str:
        try:
            if self.provider == "anthropic":
                system = next((m["content"] for m in messages if m["role"] == "system"), "")
                conv = [m for m in messages if m["role"] != "system"]
                resp = self._client.messages.create(model=self.model, max_tokens=max_tokens, system=system, messages=conv, temperature=temperature)
                return resp.content[0].text
            elif self.provider == "gemini":
                full_prompt = "\n\n".join(f"[{m['role'].upper()}]: {m['content']}" for m in messages)
                resp = self._client.generate_content(full_prompt)
                return resp.text
            else:
                resp = self._client.chat.completions.create(model=self.model, messages=messages, temperature=temperature, max_tokens=max_tokens)
                return resp.choices[0].message.content
        except Exception as e:
            # Senior logging
            console.print(f"[red]LLM Error ({self.provider}/{self.model}): {e}[/red]")
            raise e

def get_llm_client() -> LLMClient:
    config = load_config()
    provider = config.get("provider", "groq")
    api_key = get_api_key_for_provider(provider)
    
    if provider == "ollama" or api_key:
        pinfo = PROVIDERS.get(provider, {})
        return LLMClient(provider, api_key, pinfo.get("model", "llama-3.3-70b-versatile"))
    
    # Auto-detection loop
    for p in ["openai", "anthropic", "groq", "gemini"]:
        key = os.getenv(PROVIDERS[p]["env_key"], "")
        if key: return LLMClient(p, key, PROVIDERS[p]["model"])
        
    raise RuntimeError("no_provider")
