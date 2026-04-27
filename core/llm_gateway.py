"""
VibeGuard — Universal LLM Gateway v2
Routes to the best available AI provider automatically.
Priority: OpenAI → Anthropic → Groq (FREE) → Gemini (FREE) → Ollama (local)
Zero setup required — Groq free tier works out of the box.
"""

import os
from rich.console import Console
from .config_manager import load_config, get_api_key_for_provider, PROVIDERS

console = Console(force_terminal=True)


class LLMClient:
    """Unified wrapper around any LLM provider."""

    def __init__(self, provider: str, api_key: str, model: str):
        self.provider = provider
        self.model = model
        self._api_key = api_key
        self._client = None
        self._init_client()

    def _init_client(self):
        if self.provider in ("openai", "groq", "ollama"):
            from openai import OpenAI
            if self.provider == "groq":
                self._client = OpenAI(
                    api_key=self._api_key,
                    base_url="https://api.groq.com/openai/v1",
                )
            elif self.provider == "ollama":
                self._client = OpenAI(
                    base_url="http://localhost:11434/v1",
                    api_key="ollama",
                )
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
        """Universal chat interface — returns response text regardless of provider."""
        if self.provider == "anthropic":
            # Anthropic uses different message format
            system = ""
            conv_messages = []
            for m in messages:
                if m["role"] == "system":
                    system = m["content"]
                else:
                    conv_messages.append(m)
            
            resp = self._client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=conv_messages,
                temperature=temperature,
            )
            return resp.content[0].text

        elif self.provider == "gemini":
            # Gemini uses its own format
            full_prompt = "\n\n".join(
                f"[{m['role'].upper()}]: {m['content']}" for m in messages
            )
            resp = self._client.generate_content(full_prompt)
            return resp.text

        else:
            # OpenAI-compatible (openai, groq, ollama)
            resp = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return resp.choices[0].message.content


def get_llm_client() -> LLMClient:
    """
    Auto-detect best available LLM provider and return a unified client.
    
    Priority order:
      1. User's configured provider (from `vibeguard config`)
      2. Environment variable fallback for any provider
      3. Groq free tier (if GROQ_API_KEY in env)
      4. Gemini free tier (if GEMINI_API_KEY in env)
      5. Ollama local (if running)
    
    Raises RuntimeError if no provider is available.
    """
    config = load_config()
    configured_provider = config.get("provider", "")

    # 1. Try the user's configured provider first
    if configured_provider:
        api_key = get_api_key_for_provider(configured_provider)
        if configured_provider == "ollama" or api_key:
            pinfo = PROVIDERS[configured_provider]
            console.print(f"[dim]🧠 Using {pinfo['name']}[/dim]")
            return LLMClient(configured_provider, api_key, pinfo["model"])

    # 2. Auto-detect from environment variables (priority order)
    priority = ["openai", "anthropic", "groq", "gemini"]
    for provider in priority:
        pinfo = PROVIDERS[provider]
        env_key = pinfo.get("env_key")
        if env_key:
            key = os.getenv(env_key, "")
            if key and key != "your_key_here":
                console.print(f"[dim]🧠 Auto-detected {pinfo['name']} from environment[/dim]")
                return LLMClient(provider, key, pinfo["model"])

    # 3. Try Ollama as last resort
    try:
        import httpx
        r = httpx.get("http://localhost:11434/api/tags", timeout=2)
        if r.status_code == 200:
            console.print("[dim]🔒 Using Local Ollama (offline mode)[/dim]")
            return LLMClient("ollama", "", "llama3")
    except Exception:
        pass

    # 4. Nothing found — guide the user
    raise RuntimeError(
        "no_provider"
    )
