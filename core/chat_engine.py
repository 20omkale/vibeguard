"""
VibeGuard — Chat Engine
Handles multi-turn conversations with project-wide context awareness.
"""

import json
from pathlib import Path
from typing import List, Dict, Optional
from .llm_gateway import get_llm_client
from .memory_engine import generate_project_memory

class ChatEngine:
    def __init__(self, project_path: Optional[str] = None):
        self.client = get_llm_client()
        self.project_path = project_path
        self.system_prompt = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        base = (
            "You are VibeGuard AI, a Senior Staff Engineer and Project Architect. "
            "You help users build, upgrade, and debug local software projects. "
            "You are practical, concise, and focused on production-ready code. "
            "You never give placeholder code. You always consider the full project context."
        )
        
        if self.project_path:
            root = Path(self.project_path)
            memory = generate_project_memory(self.project_path)
            
            # Read uploaded context documents
            context_docs = ""
            context_dir = root / ".vibeguard" / "context"
            if context_dir.exists():
                for f in context_dir.glob("*"):
                    if f.is_file() and f.suffix.lower() in (".txt", ".md", ".json", ".py", ".js"):
                        try:
                            content = f.read_text(encoding="utf-8", errors="ignore")
                            context_docs += f"\n\n--- CONTEXT DOCUMENT: {f.name} ---\n{content[:5000]}\n"
                        except: pass
            
            base += f"\n\nCURRENT PROJECT CONTEXT:\n{memory}\n"
            if context_docs:
                base += f"\nADDITIONAL CONTEXT DOCUMENTS:\n{context_docs}\n"
            
            base += "When answering, refer to existing files, patterns, and provided context documents in this project."
            
        return base

    def get_response(self, messages: List[Dict[str, str]], stream_queue=None) -> str:
        """
        Processes a conversation history and returns the AI response.
        If stream_queue is provided, it can be used for SSE streaming (future-proofing).
        """
        # Inject system prompt at the start
        full_messages = [{"role": "system", "content": self.system_prompt}] + messages
        
        try:
            response = self.client.chat(messages=full_messages, temperature=0.3)
            return response
        except Exception as e:
            return f"Error communicating with AI: {str(e)}"

def analyze_project_gap(client, goal: str, project_path: str) -> str:
    """
    Performs a 'Gap Analysis' to identify what is missing from a project to achieve a goal.
    """
    memory = generate_project_memory(project_path)
    
    prompt = f"""You are a Lead Architect. 
Analyze the current state of this project against the user's upgrade goal.

PROJECT MEMORY:
{memory}

UPGRADE GOAL:
{goal}

Identify the 'GAP' (missing features, architectural drawbacks, or bugs).
Return a concise summary of what needs to be added or fixed to reach the goal.
Be specific about files that need creation or modification.
"""
    
    try:
        gap_analysis = client.chat(messages=[{"role": "user", "content": prompt}], temperature=0.2)
        return gap_analysis
    except Exception as e:
        return f"Gap analysis failed: {str(e)}"
