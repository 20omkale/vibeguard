# 🛡️ VibeGuard — AI-Native Developer Guardrail & Memory Agent

> **Stop losing context. Stop breaking things accidentally. Ship like a senior dev — even when you're vibe coding with AI.**

VibeGuard is a CLI tool that acts as a safety net around your AI-assisted development sessions. It maintains a persistent **PROJECT_MEMORY.md** of your codebase, detects regressions before they hit production, scores your project health, and compresses your code to fit more context into AI windows.

---

## ✨ Features

| Command | What it does |
|---------|-------------|
| `vibeguard init` | Detects your stack → generates `.cursorrules` + scaffolds `PROJECT_MEMORY.md` |
| `vibeguard scan` | Indexes your entire codebase → updates `PROJECT_MEMORY.md` |
| `vibeguard guard` | Snapshot-based regression detector — alerts on deleted exports/functions |
| `vibeguard diagnose` | Context-aware error analysis with cross-referencing against your memory |
| `vibeguard compress` | Strips your code down to essentials for AI context windows (up to 70% savings) |
| `vibeguard score` | 10,000-point project health score across 7 dimensions |
| `vibeguard status` | One-shot overview: memory freshness + health score |

---

## 🚀 Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Initialize VibeGuard in your project
cd your-project/
python vibeguard.py init

# 3. Scan your codebase
python vibeguard.py scan

# 4. Check project health
python vibeguard.py score

# 5. Before a big AI session — watch for regressions
python vibeguard.py guard
```

---

## 📋 Commands in Detail

### `vibeguard init [PATH]`
Runs stack auto-detection (Python, JS/TS, Go, Rust, Java) and generates:
- **`.cursorrules`** — Cursor AI rules tailored to your detected stack
- **`.vibeguard/stack.json`** — Stack config for future scans
- **`PROJECT_MEMORY.md`** — Scaffold (run `scan` to fully populate)

### `vibeguard scan [PATH]`
Walks your codebase and extracts:
- All functions, classes, and their signatures (with docstrings)
- Import graphs
- Open TODOs/FIXMEs
- Entry points
- Language/file breakdown stats

Outputs `PROJECT_MEMORY.md` — **paste this at the start of every AI session.**

### `vibeguard guard [PATH]`
1. Takes a snapshot of your public API surface (all exported functions/classes)
2. Waits for you to make changes
3. Diffs the before/after
4. Reports regressions by severity (HIGH/MEDIUM/INFO)
5. Generates an **AI safety prompt** you can paste into Cursor/Claude to fix issues

### `vibeguard diagnose [-e ERROR | -f FILE] [PATH]`
Matches error text against 15+ known error patterns across Python, JavaScript, and Network errors. Cross-references identifiers against `PROJECT_MEMORY.md` to find where in YOUR code the issue originates.

```bash
# Inline error
vibeguard diagnose -e "ModuleNotFoundError: No module named 'requests'"

# From a log file
vibeguard diagnose -f crash.log

# Interactive (paste + Ctrl+D)
vibeguard diagnose
```

### `vibeguard compress [PATH] [-o OUTPUT]`
Produces a single `COMPRESSED_CONTEXT.txt` file optimized for AI context windows:
- Strips Python docstrings and comments
- Strips JS/TS block and inline comments
- Collapses excessive blank lines
- Truncates base64/long string literals
- Reports per-file token savings

### `vibeguard score [PATH]`
Scores your project on a **1–10,000 point scale** across 7 dimensions:

| Dimension | Max Points |
|-----------|-----------|
| Documentation Coverage | 2,000 |
| TODO Density (inverted) | 2,000 |
| Import Health | 1,500 |
| Function Complexity | 1,500 |
| Test Coverage | 1,500 |
| Code Organization | 1,000 |
| Entry Point Clarity | 500 |
| **Total** | **10,000** |

---

## 🧠 The Philosophy

Modern vibe coding with AI is fast — but it creates **three hidden failure modes**:

1. **Lost context** — AI forgets your project structure mid-session
2. **Silent regressions** — AI deletes or renames things that other files depend on
3. **Token waste** — You're burning 40-70% of your context window on comments and whitespace

VibeGuard solves all three.

---

## 📁 Project Structure

```
vibeguard/
├── vibeguard.py              ← Main CLI entry point
├── core/
│   ├── memory_engine.py      ← Codebase scanner → PROJECT_MEMORY.md
│   ├── error_detective.py    ← Error diagnosis engine
│   ├── change_guardian.py    ← Regression detector
│   ├── context_compressor.py ← Token optimizer
│   ├── regression_tracker.py ← Health scorer (1-10,000)
│   └── initializer.py        ← Project init + .cursorrules generator
├── requirements.txt
├── .env.example
└── README.md
```

---

## 📦 Requirements

```
click>=8.1.0
rich>=13.0.0
colorama>=0.4.6
watchdog>=3.0.0
python-dotenv>=1.0.0
gitpython>=3.1.0
```

Python 3.10+ required.

---

## 🔧 Advanced Usage

### Run against a specific project
```bash
python vibeguard.py scan /path/to/my-project
python vibeguard.py score /path/to/my-project
```

### Diagnose from a log file
```bash
# Save your terminal output to a file, then analyze it
python vibeguard.py diagnose -f error_output.log /path/to/my-project
```

### Compress and copy to clipboard (Windows)
```bash
python vibeguard.py compress && type COMPRESSED_CONTEXT.txt | clip
```

---

## 🤝 Contributing

VibeGuard is built to be extended. Each core module is independent and testable. To add a new error pattern, edit the `ERROR_PATTERNS` list in `core/error_detective.py`.

---

*Built with ❤️ to make vibe coding safer.*
