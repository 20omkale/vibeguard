"""
VibeGuard — Telemetry Engine
Securely logs anonymized build metrics to create a Data Flywheel.
"""

import os
import json
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime
from rich.console import Console

console = Console()

def send_telemetry(prompt: str, architecture: dict, success: bool, error_logs: str = ""):
    """
    Sends build telemetry to the central database (if configured) and saves it locally
    for the agent to learn from (Data Flywheel).
    """
    payload = {
        "timestamp": datetime.utcnow().isoformat(),
        "prompt": prompt,
        "stack": architecture.get("stack", "unknown"),
        "files_generated": len(architecture.get("files", {})),
        "success": success,
        "error_logs": error_logs
    }

    # 1. Save to Local Knowledge Base (RAG Flywheel)
    try:
        kb_dir = Path.home() / ".vibeguard"
        kb_dir.mkdir(parents=True, exist_ok=True)
        kb_file = kb_dir / "global_learnings.json"
        
        learnings = []
        if kb_file.exists():
            with open(kb_file, "r", encoding="utf-8") as f:
                learnings = json.load(f)
                
        learnings.append(payload)
        # Keep only the last 50 learnings to prevent context bloat
        learnings = learnings[-50:]
        
        with open(kb_file, "w", encoding="utf-8") as f:
            json.dump(learnings, f, indent=2)
    except Exception as e:
        console.print(f"[dim]⚠️ Local Knowledge Base update failed: {e}[/dim]")

    # 2. Sync to Cloud Database Webhook
    db_url = os.getenv("VIBEGUARD_TELEMETRY_URL")
    if not db_url or db_url == "your_database_webhook_url_here":
        return

    try:
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            db_url,
            data=data,
            headers={'Content-Type': 'application/json', 'User-Agent': 'VibeGuard-Agent/1.0'}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status in (200, 201):
                console.print("[dim]📡 Telemetry synced to central database.[/dim]")
    except Exception as e:
        console.print(f"[dim]⚠️ Telemetry sync failed: {e}[/dim]")
