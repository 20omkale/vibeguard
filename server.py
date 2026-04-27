"""
VibeGuard Web Server
Launches a local web dashboard at http://localhost:7456
Real-time streaming output via Server-Sent Events (SSE).
"""

import json
import queue
import threading
import webbrowser
import time
import sys
import io
from pathlib import Path
from flask import Flask, request, jsonify, Response, send_from_directory
from flask_cors import CORS

# ── App setup ─────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
UI_DIR   = BASE_DIR / "ui"

app = Flask(__name__, static_folder=str(UI_DIR), static_url_path="")
CORS(app)

# ── SSE streaming ──────────────────────────────────────────────────────────────

class StreamCapture(io.TextIOBase):
    """Captures Rich console output and puts it into a queue for SSE streaming."""
    def __init__(self, q: queue.Queue):
        self.q = q

    def write(self, text: str) -> int:
        if text and text.strip():
            self.q.put({"type": "log", "text": text.rstrip()})
        return len(text)

    def flush(self):
        pass


def sse_stream(task_fn, *args, **kwargs):
    """Run task_fn in a thread and stream output as SSE."""
    q: queue.Queue = queue.Queue()

    def run():
        # Redirect Rich console output to SSE queue
        from rich.console import Console
        import core.llm_gateway as gw
        import core.autonomous_agent as aa
        import core.project_genesis as pg
        import core.session_protector as sp
        import core.error_detective as ed
        import core.config_manager as cm

        stream = StreamCapture(q)
        patched_console = Console(file=stream, force_terminal=False, highlight=False, markup=False)

        # Monkey-patch all module consoles
        for mod in [gw, aa, pg, sp, ed, cm]:
            if hasattr(mod, "console"):
                mod.console = patched_console

        try:
            task_fn(q, *args, **kwargs)
        except Exception as e:
            q.put({"type": "error", "text": str(e)})
        finally:
            q.put({"type": "done"})

    t = threading.Thread(target=run, daemon=True)
    t.start()

    def generate():
        while True:
            try:
                item = q.get(timeout=60)
                yield f"data: {json.dumps(item)}\n\n"
                if item.get("type") == "done":
                    break
            except queue.Empty:
                yield f"data: {json.dumps({'type': 'ping'})}\n\n"

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(str(UI_DIR), "index.html")


@app.route("/api/status", methods=["GET"])
def status():
    from core.config_manager import load_config, is_configured, PROVIDERS
    config = load_config()
    provider = config.get("provider", "")
    pname = PROVIDERS.get(provider, {}).get("name", "Not configured") if provider else "Not configured"
    return jsonify({
        "configured": is_configured(),
        "provider": provider,
        "provider_name": pname,
        "version": "2.0.0",
    })


@app.route("/api/config", methods=["GET"])
def get_config():
    from core.config_manager import load_config, PROVIDERS
    config = load_config()
    return jsonify({"config": config, "providers": {k: v["name"] for k, v in PROVIDERS.items()}})


@app.route("/api/config", methods=["POST"])
def set_config():
    data = request.json or {}
    provider = data.get("provider", "")
    api_key  = data.get("api_key", "").strip()

    from core.config_manager import load_config, save_config, PROVIDERS, _validate_key
    config = load_config()
    config["provider"] = provider

    if provider != "ollama" and api_key:
        pinfo = PROVIDERS.get(provider, {})
        valid, err = _validate_key(provider, api_key, pinfo.get("model", ""))
        if not valid:
            return jsonify({"ok": False, "error": err}), 400
        config.setdefault("api_keys", {})[provider] = api_key

    save_config(config)
    return jsonify({"ok": True})


@app.route("/api/genesis", methods=["POST"])
def genesis():
    data   = request.json or {}
    idea   = data.get("idea", "").strip()
    answers = data.get("answers", {})

    if not idea:
        return jsonify({"error": "No idea provided"}), 400

    def task(q, idea, answers):
        from core.llm_gateway import get_llm_client
        from core.project_genesis import (
            _generate_prd, _generate_architecture, _generate_database_schema,
            _generate_api_spec, _generate_dev_plan, _generate_ai_prompt,
            _generate_cursor_rules, _format_answers,
        )
        import tempfile, os

        try:
            client = get_llm_client()
        except RuntimeError:
            q.put({"type": "error", "text": "No AI provider configured. Go to Settings first."})
            return

        # Build enriched prompt from answers
        enriched = {"raw_idea": idea, **answers}

        output_dir = Path.home() / "VibeGuard_Projects" / idea[:30].replace(" ", "-")
        output_dir.mkdir(parents=True, exist_ok=True)

        steps = [
            ("PRD.md", "Writing Product Requirements Document...", _generate_prd),
            ("ARCHITECTURE.md", "Designing System Architecture...", _generate_architecture),
            ("DATABASE_SCHEMA.md", "Designing Database Schema...", _generate_database_schema),
            ("API_SPEC.md", "Writing API Specification...", _generate_api_spec),
            ("DEV_PLAN.md", "Creating Development Plan...", _generate_dev_plan),
            ("AI_PROMPTS.md", "Crafting AI Prompts...", _generate_ai_prompt),
            (".cursorrules", "Generating Project Rules...", _generate_cursor_rules),
        ]

        results = []
        for filename, msg, fn in steps:
            q.put({"type": "step", "text": msg})
            try:
                fn(client, enriched, output_dir)
                q.put({"type": "success", "text": f"✓ {filename}"})
                results.append(filename)
            except Exception as e:
                q.put({"type": "warn", "text": f"✗ {filename}: {str(e)[:80]}"})

        q.put({"type": "result", "data": {
            "output_dir": str(output_dir),
            "files": results,
        }})

    return sse_stream(task, idea, answers)


@app.route("/api/genesis/questions", methods=["POST"])
def genesis_questions():
    """Get interview questions for the genesis flow."""
    data = request.json or {}
    idea = data.get("idea", "").strip()
    if not idea:
        return jsonify({"questions": []}), 200

    try:
        from core.llm_gateway import get_llm_client
        client = get_llm_client()
        prompt = f"""You are a Senior PM. Given idea: "{idea}"
Generate 5 short questions to clarify exactly what to build.
Return ONLY JSON: {{"questions": [{{"id":1,"question":"...","default":"..."}}]}}"""
        response = client.chat(messages=[{"role": "user", "content": prompt}], temperature=0.3, max_tokens=600)

        import re
        text = response
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        data_out = json.loads(text.strip())
        return jsonify(data_out)
    except Exception as e:
        return jsonify({"questions": [], "error": str(e)}), 200


@app.route("/api/build", methods=["POST"])
def build():
    data   = request.json or {}
    prompt = data.get("prompt", "").strip()
    target = data.get("target_dir", str(Path.home() / "VibeGuard_Projects"))

    if not prompt:
        return jsonify({"error": "No prompt provided"}), 400

    def task(q, prompt, target):
        # Redirect all prints to SSE
        from rich.console import Console
        stream = StreamCapture(q)
        console = Console(file=stream, force_terminal=False, highlight=False, markup=False)

        try:
            from core.llm_gateway import get_llm_client
            from core.autonomous_agent import (
                _architect_project, _code_phase, _install_phase,
            )
            client = get_llm_client()

            q.put({"type": "step", "text": "Planning architecture..."})
            architecture = _architect_project(client, prompt)
            if not architecture:
                q.put({"type": "error", "text": "Architecture planning failed."})
                return

            q.put({"type": "step", "text": f"Generating {len(architecture.get('files', {}))} files..."})
            root = Path(target)
            root.mkdir(parents=True, exist_ok=True)
            _code_phase(client, architecture, root, prompt)

            q.put({"type": "step", "text": "Installing dependencies..."})
            _install_phase(architecture, root)

            q.put({"type": "result", "data": {
                "output_dir": str(root),
                "run_command": architecture.get("run_command", ""),
                "stack": architecture.get("stack", ""),
                "files": list(architecture.get("files", {}).keys()),
            }})
        except RuntimeError:
            q.put({"type": "error", "text": "No AI provider configured. Go to Settings."})
        except Exception as e:
            q.put({"type": "error", "text": str(e)})

    return sse_stream(task, prompt, target)


@app.route("/api/diagnose", methods=["POST"])
def diagnose():
    data  = request.json or {}
    error = data.get("error", "").strip()
    path  = data.get("project_path", ".").strip() or "."

    if not error:
        return jsonify({"error": "No error text provided"}), 400

    def task(q, error_text, project_path):
        try:
            from core.error_detective import run_diagnose
            # Capture output
            stream = StreamCapture(q)
            import core.error_detective as ed
            from rich.console import Console
            ed.console = Console(file=stream, force_terminal=False, highlight=False, markup=False)
            run_diagnose(error_text, project_path)
        except RuntimeError:
            q.put({"type": "error", "text": "No AI provider configured. Go to Settings."})
        except Exception as e:
            q.put({"type": "error", "text": str(e)})

    return sse_stream(task, error, path)


@app.route("/api/protect/before", methods=["POST"])
def protect_before():
    data = request.json or {}
    path = data.get("path", ".").strip() or "."

    def task(q, path):
        try:
            from core.session_protector import CodeSnapshot, _save_snapshot
            q.put({"type": "step", "text": "Scanning all files..."})
            snap = CodeSnapshot(Path(path))
            _save_snapshot(snap, Path(path), "session")
            total_funcs  = sum(len(v) for v in snap.functions.values())
            total_routes = sum(len(v) for v in snap.routes.values())
            q.put({"type": "result", "data": {
                "files":     len(snap.functions),
                "functions": total_funcs,
                "routes":    total_routes,
                "timestamp": snap.timestamp,
            }})
        except Exception as e:
            q.put({"type": "error", "text": str(e)})

    return sse_stream(task, path)


@app.route("/api/protect/after", methods=["POST"])
def protect_after():
    data = request.json or {}
    path = data.get("path", ".").strip() or "."

    def task(q, path):
        try:
            from core.session_protector import (
                CodeSnapshot, SessionDiff, _load_latest_snapshot, _generate_restore_prompt
            )
            before = _load_latest_snapshot(Path(path), "session")
            if not before:
                q.put({"type": "error", "text": "No baseline found. Run 'Protect Before' first."})
                return

            q.put({"type": "step", "text": "Scanning current state..."})
            after = CodeSnapshot(Path(path))
            diff  = SessionDiff(before, after)

            q.put({"type": "result", "data": {
                "severity":          diff.severity,
                "is_clean":          diff.is_clean,
                "deleted_functions": diff.deleted_functions,
                "modified_functions":diff.modified_functions,
                "deleted_routes":    diff.deleted_routes,
                "deleted_exports":   diff.deleted_exports,
            }})
        except Exception as e:
            q.put({"type": "error", "text": str(e)})

    return sse_stream(task, path)


# ── Launch ─────────────────────────────────────────────────────────────────────

def start_server(port: int = 7456, open_browser: bool = True):
    """Start the VibeGuard web dashboard."""
    if open_browser:
        def _open():
            time.sleep(1.2)
            webbrowser.open(f"http://localhost:{port}")
        threading.Thread(target=_open, daemon=True).start()

    print(f"\n  VibeGuard Dashboard → http://localhost:{port}\n  Press Ctrl+C to stop.\n")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False, threaded=True)


if __name__ == "__main__":
    start_server()
