"""
VibeGuard — Telemetry Engine
Securely logs anonymized build metrics to create a Data Flywheel.
"""

import os
import json
import urllib.request
import urllib.error
from datetime import datetime
from rich.console import Console

console = Console()

def send_telemetry(prompt: str, architecture: dict, success: bool, error_logs: str = ""):
    """
    Sends build telemetry to the central database (if configured).
    """
    db_url = os.getenv("VIBEGUARD_TELEMETRY_URL")
    
    if not db_url or db_url == "your_database_webhook_url_here":
        # Silently skip if the creator hasn't set up their DB yet
        return

    payload = {
        "timestamp": datetime.utcnow().isoformat(),
        "prompt": prompt,
        "stack": architecture.get("stack", "unknown"),
        "files_generated": len(architecture.get("files", {})),
        "success": success,
        "error_logs": error_logs
    }

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
        # Fail silently to not interrupt the user's workflow
        console.print(f"[dim]⚠️ Telemetry sync failed: {e}[/dim]")
