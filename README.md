<div align="center">

# TerminalX EcoSystem

[![Python](https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey?style=flat-square)](https://github.com/polsoft-seb07uk)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow?style=flat-square)](https://opensource.org/licenses/MIT)
[![Modules](https://img.shields.io/badge/core%20modules-45-5c7cfa?style=flat-square)](./core/)
[![LOC](https://img.shields.io/badge/lines%20of%20code-53%2C000%2B-success?style=flat-square)](./core/)
[![Brand](https://img.shields.io/badge/polsoft.ITS%E2%84%A2-Group-9c27b0?style=flat-square)](mailto:polsoft.its@fastservice.com)

**A modular, self-integrating Python terminal that operates as a single living organism.**  
Not a shell wrapper. Not a plugin manager. An ecosystem.

[Getting Started](#getting-started) · [Modules](#modules) · [Architecture](#architecture) · [Configuration](#configuration) · [Tests](#tests) · [Contributing](#contributing)

</div>

---

## What is TerminalX?

TerminalX is a terminal application written entirely in Python that replaces the fragmented stack of CLI utilities with one cohesive runtime. Every component — file management, network diagnostics, package installation, code analysis, AI assistant, SSH client, virtual drives, and more — is a **core module** that loads, integrates, and communicates natively.

The entry point is a single file:

```python
# TerminalX.py
from core import TerminalX

if __name__ == "__main__":
    terminal = TerminalX()
    terminal.run()
```

Everything else is the organism.

---

## Getting Started

### Requirements

- Python **3.10+** (3.11+ recommended)
- Windows 10/11 · Linux · macOS

External tools called by subprocess (all optional):

| Tool | Used by |
|---|---|
| `ping` | net_diag — built into most OSes |
| `npm` / `node` | pkg — Node.js package installation |
| `bash` / `sh` | scripts — shell script execution |
| `powershell` / `pwsh` | scripts — PowerShell execution on Windows |

### Install

```bash
git clone https://github.com/polsoft-seb07uk/EcoSystem.git
cd EcoSystem
```

No virtual environment required. TerminalX manages its own library space.

### Run

```bash
python TerminalX.py
```

Or install dependencies first if you want the full feature set:

```
install libs
```

This reads `libs/requirements.txt` and installs packages to `libs/pip/`.

### GUI mode

```bash
python gui/app.py
```

---

## Modules

TerminalX ships **45 core modules**. They load in dependency order at startup and register their commands into the shared terminal instance.

### Foundation

| Module | Description |
|---|---|
| `lang` | i18n engine — Polish / English, runtime language switching |
| `config` | Persistent configuration, shared across all modules |
| `ansi` | ANSI/VT escape rendering, True Color detection, Windows VTP init |
| `colors` | Color utilities and palette tools |
| `runner` | Interpreter discovery for 30+ file types (.py .js .sh .ps1 .rb ...) |
| `notify` | Multi-channel notifications: desktop, SMTP, Slack, Discord, Teams |
| `debugger` | Event logging, process memory stats, runtime diagnostics |
| `history` | Command history with search and persistence |
| `alias` | Command aliases with persistence |
| `cache` | Shared cache engine used by analyser, pkg, and others |

### Security

| Module | Description |
|---|---|
| `defender` | File integrity via SHA-256, quarantine, threat classification |
| `sha256` | Hash computation engine — used by defender, analyser, scripts |
| `sandbox` | Isolated script execution with dry-run, profiles, rate limiting |

### File System

| Module | Description |
|---|---|
| `command` | File operations: copy, move, rename, stat, diff, chmod, ln, tee |
| `trash` | Safe delete with restore — cross-platform recycle bin |
| `vdrive` | Virtual drives: ISO mounting, VHD creation, snapshots |
| `scripts` | Script runner with AST-based import detection and sandboxing |
| `docs` | Document management and report generation |
| `search` | File and content search with filtering |

### Network

| Module | Description |
|---|---|
| `net_diag` | IP info, DNS lookup, port scan, routing, traceroute, latency |
| `wifi` | WiFi scanner with IEEE OUI database and TCP verification |
| `ssh` | SSH / SFTP client (requires `paramiko`) |
| `github` | GitHub API client — repos, issues, gists, PAT authentication |

### Package Management

| Module | Description |
|---|---|
| `pkg` | Package manager: pip, npm, GitHub releases, direct URL |
| `virtual_env` | Python virtual environment inside the terminal — isolated libs |

### Development & Analysis

| Module | Description |
|---|---|
| `analyser` | Static code analysis: per-function metrics, call graph, dead code, lint |
| `tools` | Developer utilities |
| `syntax_highlight` | Syntax highlighting for source files |
| `math_engine` | Mathematical computation engine |
| `imgtools` | Image conversion, thumbnails, format detection |

### System & Monitoring

| Module | Description |
|---|---|
| `monitor` | Real-time CPU, RAM, disk, network monitor |
| `admin` | System administration: fs, net, sec, data, processes |
| `task` | Task scheduler with day-of-week rules and background execution |
| `env` | Environment variable management |
| `switch` | Runtime mode toggles |
| `tests` | Built-in test runner with dynamic discovery and persistent results |

### Productivity

| Module | Description |
|---|---|
| `ai` | AI assistant — 30+ models, presets, GUI chat window |
| `cal` | Calendar and date utilities |
| `qr` | QR code, barcode, and NFC tag generator |
| `video_downloader` | Video downloader (yt-dlp wrapper) |
| `help` | Command reference and module help |
| `modmenu` | Module discovery menu (`??`) |

---

## Architecture

### The integration bridge

Modules never import each other directly. All cross-module calls go through `core/_integration.py`:

```python
# Register your API (in setup())
from . import _integration
_integration.register("sha256", {
    "compute":  _compute_hash,
    "compare":  _compare_hashes,
})

# Call another module's API (from anywhere)
digest = _integration.call("sha256", "compute", path)

# Check availability first
if _integration.is_available("ai"):
    response = _integration.call("ai", "send_message", "hello")
```

This eliminates circular imports and makes every dependency optional. If a module isn't loaded, `call()` returns the `default` — it never raises.

### Load order

Modules load in a dependency-aware sequence defined in `core/__init__.py`:

```
lang → config → ansi → sha256 → runner → notify
  → debugger → defender → trash → vdrive → history → alias
  → cache → search → tools → scripts → sandbox → analyser
  → imgtools → math_engine → task → pkg → virtual_env
  → docs → net_diag → ssh → github → env → switch
  → syntax_highlight → command → colors → help → modmenu
  → tests → monitor → admin → video_downloader → ai
```

Modules marked as sequential load one at a time. The rest load in parallel via `ThreadPoolExecutor`.

### Module anatomy

Every core module follows the same contract:

```python
def setup(terminal) -> None:
    """Called once on load. Register commands and publish API."""
    _integration.register("mymodule", { "fn": my_fn })
    terminal.register_command("mycmd", handler, description=..., category=...)

def teardown(terminal) -> None:
    """Called on unload. Clean up."""
    _integration.unregister("mymodule")
    terminal.commands.pop("mycmd", None)
```

### Project layout

```
EcoSystem/
├── TerminalX.py          # entry point
├── core/                 # 45 core modules
│   ├── __init__.py       # loader, TerminalX class, load order
│   ├── _integration.py   # cross-module service registry
│   ├── _shared.py        # constants: ROOT_DIR, ANSI codes, helpers
│   ├── config.py
│   ├── pkg.py
│   ├── virtual_env.py
│   └── ...
├── lang/
│   ├── en.py             # English translations
│   └── pl.py             # Polish translations
├── gui/
│   └── app.py            # tkinter GUI shell
├── modules/              # user-created modules (auto-discovered)
├── plugins/              # plugin directory
├── scripts/              # user scripts
│   └── logs/
├── libs/
│   ├── requirements.txt
│   └── pip/              # pip packages installed by `install libs`
├── docs/
│   └── reports/          # generated reports (monitor, analyser)
├── tests/
│   ├── test_core.py
│   ├── test_i18n.py
│   └── test_terminalx.py
├── tools/
├── key/
│   └── api_keys.ini      # API keys (AI, GitHub PAT, etc.)
└── .cache/               # runtime cache (JSON, per-module)
```

---

## Configuration

All configuration lives in `~/.crossterm/config.json`. Each module owns a named section:

```json
{
  "lang":    { "language": "pl" },
  "config":  { "theme": "dark", "prompt": "> " },
  "venv":    { "library_sources": {}, "extra_paths": [], "autoload": false },
  "ai":      { "active_profile": "openai-gpt4", "profiles": {} },
  "task":    { "jobs": [] },
  "defender":{ "quarantine_path": ".quarantine", "hash_checks": true }
}
```

There is no race condition on writes — every module writes its section through the shared config writer, never the full file directly.

### API keys

Stored in `key/api_keys.ini` (not committed to version control):

```ini
[openai]
api_key = sk-...

[anthropic]
api_key = sk-ant-...

[github]
token = ghp_...
```

---

## Language support

TerminalX ships with full **Polish and English** translations. Every user-facing string goes through `terminal.t("key")`. Switch at runtime:

```
lang en
lang pl
```

Translation files are in `lang/en.py` and `lang/pl.py`. Each contains a flat dictionary of ~1500+ keys.

---

## Virtual Environment

TerminalX maintains its own isolated Python library space at `~/.crossterm/venv/lib`, separate from the system Python. Managed by the `virtual_env` core module:

```
venv install requests           # install to ~/.crossterm/venv/lib
venv install pillow --with-deps
venv list                       # show all libs and their resolution source
venv apply                      # add venv paths to sys.path (current session)
venv autoload on                # apply automatically on every start
venv sync requirements.txt      # bulk install from file
venv freeze                     # export as requirements.txt
```

Resolution priority per library: `ecosystem → os` (configurable per-lib via `venv set <lib> os|ecosystem|auto`).

---

## Tests

144 test cases across three suites:

```bash
# Run all tests from within TerminalX
tests run

# Or directly with pytest
pytest tests/
```

| File | Tests | Coverage |
|---|---|---|
| `tests/test_core.py` | 41 | Core modules, config, cache, hash, trash |
| `tests/test_i18n.py` | 61 | Translation completeness, key parity EN/PL |
| `tests/test_terminalx.py` | 42 | Command registration, history, alias, runner |

---

## Extending TerminalX

### User modules

Drop a `.py` file into `modules/`. It must expose `setup(terminal)`:

```python
# modules/my_tool.py
def setup(terminal):
    def hello(args):
        print("Hello from my module!")

    terminal.register_command(
        "hello", hello,
        description="My custom command",
        category=terminal.t("cat_modules"),
    )
```

TerminalX auto-discovers all files in `modules/` on startup.

### User plugins

The `plugins/` directory follows the same convention and supports hot-reload.

---

## Dependencies

### Required

| Package | Version | Purpose |
|---|---|---|
| `psutil` | ≥ 5.9.0 | Process management, system stats (runner, debugger, monitor) |
| `colorama` | ≥ 0.4.6 | ANSI fallback on older Windows terminals |

### Optional (uncomment in `libs/requirements.txt`)

| Package | Enables |
|---|---|
| `paramiko` | SSH / SFTP client |
| `prompt_toolkit` | Advanced tab completion, inline history |
| `rich` | Rich table and progress bar rendering |
| `pygments` | Syntax highlighting |
| `requests` | Cleaner HTTP in net_diag and pkg |
| `dnspython` | Extended DNS queries (MX, TXT, AAAA) |
| `send2trash` | Native trash on Linux / macOS |
| `watchdog` | Directory monitoring for defender |
| `pywin32` | Advanced Win32 API (Windows only) |

### Build / dev

```
pyinstaller  nuitka  black  flake8  mypy  pytest
```

---

## Author

**Sebastian Januchowski**  
[polsoft.ITS™ Group](mailto:polsoft.its@fastservice.com) · GitHub: [@polsoft-seb07uk](https://github.com/polsoft-seb07uk)

---

## License

[MIT](https://opensource.org/licenses/MIT) © polsoft.ITS™ Group
