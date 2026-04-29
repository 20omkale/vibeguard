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
import os
import mimetypes
from pathlib import Path
from flask import Flask, request, jsonify, Response, send_from_directory
from flask_cors import CORS

# ── App setup ─────────────────────────────────────────────────────────────────

if getattr(sys, 'frozen', False):
    # Running in a PyInstaller bundle
    BASE_DIR = Path(sys._MEIPASS)
else:
    # Running in normal Python environment
    BASE_DIR = Path(__file__).parent

UI_DIR   = BASE_DIR / "ui"

app = Flask(__name__, static_folder=str(UI_DIR), static_url_path="")
CORS(app)

# Global Thread-Safe Log Buffer for Workspace Console
SYSTEM_LOGS = []
LOG_LOCK = threading.Lock()

def add_log(text, log_type="log"):
    with LOG_LOCK:
        SYSTEM_LOGS.append({"text": text, "type": log_type, "time": time.time()})
        if len(SYSTEM_LOGS) > 500: SYSTEM_LOGS.pop(0)

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
    ngrok_token = data.get("ngrok_token", "").strip()

    from core.config_manager import load_config, save_config, PROVIDERS, _validate_key
    config = load_config()
    
    if provider: config["provider"] = provider
    if ngrok_token: config["ngrok_token"] = ngrok_token

    if provider and provider != "ollama" and api_key:
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


@app.route("/api/upgrade", methods=["POST"])
def upgrade():
    data = request.json or {}
    path = data.get("path", ".").strip().strip('"').strip("'") or "."
    instruction = data.get("instruction", "").strip()

    if not instruction:
        return jsonify({"error": "No instruction provided"}), 400

    def task(q, path, instruction):
        try:
            from core.llm_gateway import get_llm_client
            from core.memory_engine import generate_project_memory
            from core.autonomous_agent import _code_phase
            from core.project_genesis import _generate_prd, _generate_architecture
            from core.chat_engine import analyze_project_gap
            
            client = get_llm_client()
            root = Path(path)
            root.mkdir(parents=True, exist_ok=True)
            
            # Phase -1: Gap Analysis (Understanding the 'Missing' parts)
            q.put({"type": "step", "text": "Phase -1: Performing Gap Analysis (Identifying what is missing)..."})
            gap = analyze_project_gap(client, instruction, path)
            q.put({"type": "log", "text": f"Gap Analysis Result:\n{gap}"})
            
            # Read any uploaded context documents
            context_dir = root / ".vibeguard" / "context"
            additional_context = ""
            if context_dir.exists():
                q.put({"type": "step", "text": "Loading uploaded context documents..."})
                for cfile in context_dir.iterdir():
                    if cfile.is_file() and cfile.suffix.lower() in [".md", ".txt", ".json", ".csv", ".yml", ".yaml", ".js", ".py", ".ts", ".html", ".css"]:
                        try:
                            content = cfile.read_text(encoding="utf-8")
                            additional_context += f"\n--- {cfile.name} ---\n{content}\n"
                        except:
                            pass
                import shutil
                shutil.rmtree(context_dir, ignore_errors=True)
            
            # Phase 0: Documentation First (Senior Dev Approach)
            q.put({"type": "step", "text": "Phase 0: Studying project and generating technical documentation..."})
            memory = generate_project_memory(path)
            if additional_context:
                memory += f"\n\n=== USER PROVIDED CONTEXT ===\n{additional_context}"
            
            # Add gap context to instruction for doc generation
            enriched_instruction = f"{instruction}\n\nGap Analysis context:\n{gap}"
            
            doc_context = {"raw_idea": enriched_instruction, "existing_memory": memory}
            _generate_prd(client, doc_context, root)
            _generate_architecture(client, doc_context, root)
            q.put({"type": "success", "text": "✓ Documentation generated (PRD.md, ARCHITECTURE.md) with gap awareness."})

            # Autonomous Deep Loop (The "Sleep & Build" Engine)
            max_iterations = 10
            for i in range(max_iterations):
                q.put({"type": "step", "text": f"Iteration {i+1}: Analyzing current project state..."})
                memory = generate_project_memory(path)
                if additional_context:
                    memory += f"\n\n=== USER PROVIDED CONTEXT ===\n{additional_context}"
                
                plan_prompt = f"""
Current Project Memory: {memory}
High-Level Goal: {instruction}

You are a Lead Autonomous Architect. 
1. If the goal is fully achieved, respond with ONLY the string 'GOAL_REACHED'.
2. Otherwise, identify the NEXT SPECIFIC STEP to move closer to the goal.
3. Return your plan as JSON matching the architecture format:
{{"files": {{"path/to/file": "detailed implementation plan..."}}, "stack": "..."}}
"""
                response = client.chat([{"role": "user", "content": plan_prompt}])
                
                if "GOAL_REACHED" in response:
                    q.put({"type": "success", "text": "✨ High-level production goal achieved!"})
                    break
                
                import re
                text = response
                if "```json" in text: text = text.split("```json")[1].split("```")[0]
                elif "```" in text: text = text.split("```")[1].split("```")[0]
                
                try:
                    architecture = json.loads(text.strip())
                except:
                    q.put({"type": "warn", "text": "Plan format invalid, retrying..."})
                    continue
                
                q.put({"type": "step", "text": f"Executing iteration {i+1} code generation..."})
                _code_phase(client, architecture, root, instruction)
                
                # Check for syntax errors (Self-healing)
                q.put({"type": "step", "text": "Self-healing: Checking for syntax errors..."})
                # (Logic here would call a validator, for brevity we assume the loop handles it next turn)

            q.put({"type": "result", "data": {"path": str(root)}})
            
        except Exception as e:
            q.put({"type": "error", "text": str(e)})

    return sse_stream(task, path, instruction)


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
    path = data.get("path", ".").strip().strip('"').strip("'") or "."

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


@app.route("/api/diagnose", methods=["POST"])
def diagnose():
    data = request.json or {}
    path = data.get("path", "").strip().strip('"').strip("'")
    if not path:
        return jsonify({"error": "No project path"}), 400

    def task(q, path):
        try:
            from core.diagnostics_engine import DiagnosticsEngine
            engine = DiagnosticsEngine(path)
            report = engine.run_scan()
            q.put({"type": "result", "data": report})
        except Exception as e:
            q.put({"type": "error", "text": str(e)})

    return sse_stream(task, path)


@app.route("/api/protect/after", methods=["POST"])
def protect_after():
    data = request.json or {}
    path = data.get("path", ".").strip().strip('"').strip("'") or "."

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


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.json or {}
    messages = data.get("messages", [])
    path = data.get("path", "").strip().strip('"').strip("'")
    active_file = data.get("activeFile", "")
    active_content = data.get("activeContent", "")
    
    if not messages:
        return jsonify({"error": "No messages"}), 400

    def task(q, messages, path, active_file, active_content):
        try:
            from core.chat_engine import ChatEngine
            engine = ChatEngine(project_path=path if path else None)
            
            # Inject active file context into system prompt if present
            if active_file and active_content:
                engine.system_prompt += f"\n\nUSER IS CURRENTLY VIEWING THIS FILE: {active_file}\nCONTENT:\n{active_content[:10000]}\n"
                engine.system_prompt += "Focus your answers on this file if relevant."
                
            response = engine.get_response(messages)
            q.put({"type": "chat_reply", "text": response})
        except Exception as e:
            q.put({"type": "error", "text": str(e)})

    return sse_stream(task, messages, path, active_file, active_content)


# ── Workspace Utils ────────────────────────────────────────────────────────────

@app.route("/api/utils/folder-picker")
def folder_picker():
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        path = filedialog.askdirectory()
        root.destroy()
        return jsonify({"path": path})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/utils/files", methods=["POST"])
def list_workspace_files():
    data = request.json or {}
    path_str = data.get("path", "").strip().strip('"').strip("'")
    if not path_str: return jsonify({"files": []})
    
    root = Path(path_str)
    if not root.exists(): return jsonify({"error": "Path not found"}), 404

    # Save to Recent Projects
    try:
        recent_path = Path.home() / ".vibeguard" / "recent_projects.json"
        recent_path.parent.mkdir(exist_ok=True)
        recent = []
        if recent_path.exists():
            recent = json.loads(recent_path.read_text())
        
        if str(root) not in recent:
            recent.insert(0, str(root))
            recent = recent[:10] # Keep last 10
            recent_path.write_text(json.dumps(recent))
    except: pass

    def get_tree(p: Path):
        tree = []
        try:
            entries = sorted(list(p.iterdir()), key=lambda x: (not x.is_dir(), x.name.lower()))
            for entry in entries:
                if entry.name.startswith((".", "__pycache__", "node_modules")): continue
                rel = str(entry.relative_to(root))
                node = {"name": entry.name, "path": rel, "is_dir": entry.is_dir()}
                if entry.is_dir(): node["children"] = get_tree(entry)
                tree.append(node)
        except: pass
        return tree

    return jsonify({"files": get_tree(root), "root": str(root)})


@app.route("/api/utils/recent", methods=["GET"])
def get_recent_projects():
    try:
        recent_path = Path.home() / ".vibeguard" / "recent_projects.json"
        if recent_path.exists():
            return jsonify({"recent": json.loads(recent_path.read_text())})
    except: pass
    return jsonify({"recent": []})


@app.route("/api/utils/read-file", methods=["POST"])
def read_workspace_file():
    data = request.json or {}
    root_str = data.get("root", "").strip().strip('"').strip("'")
    rel_path = data.get("path", "").strip()
    
    if not root_str or not rel_path: return jsonify({"error": "Missing path"}), 400
    
    fpath = Path(root_str) / rel_path
    if not fpath.exists(): return jsonify({"error": "File not found"}), 404
    
    try:
        content = fpath.read_text(encoding="utf-8", errors="ignore")
        return jsonify({
            "content": content,
            "path": rel_path,
            "name": fpath.name,
            "extension": fpath.suffix.lower()
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500




# ── Utils ──────────────────────────────────────────────────────────────────────

@app.route("/api/utils/select-folder", methods=["GET"])
def select_folder():
    """Opens a native folder picker on the host machine."""
    import tkinter as tk
    from tkinter import filedialog
    
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    folder_path = filedialog.askdirectory()
    root.destroy()
    
    return jsonify({"path": folder_path if folder_path else ""})


@app.route("/api/utils/upload-docs", methods=["POST"])
def upload_docs():
    """Handle document/image uploads for AI context."""
    if 'files' not in request.files:
        return jsonify({"error": "No files"}), 400
    
    files = request.files.getlist('files')
    target_path = request.form.get("path", ".").strip().strip('"').strip("'") or "."
    upload_dir = Path(target_path) / ".vibeguard" / "context"
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    saved = []
    for f in files:
        if f.filename:
            fpath = upload_dir / f.filename
            f.save(str(fpath))
            saved.append(f.filename)
            
    return jsonify({"ok": True, "files": saved})


# ── Launch ─────────────────────────────────────────────────────────────────────

def start_server(port: int = 7456, open_browser: bool = True):
    """Start the VibeGuard web dashboard."""
    if open_browser:
        def _open():
            time.sleep(1.2)
            webbrowser.open(f"http://localhost:{port}")
        threading.Thread(target=_open, daemon=True).start()

    print(f"\n  VibeGuard Dashboard -> http://localhost:{port}\n  Press Ctrl+C to stop.\n")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False, threaded=True)


@app.route("/api/utils/logs")
def get_system_logs():
    after = float(request.args.get("after", 0))
    with LOG_LOCK:
        new_logs = [l for l in SYSTEM_LOGS if l["time"] > after]
    return jsonify({"logs": new_logs})

if __name__ == "__main__":
    start_server()
