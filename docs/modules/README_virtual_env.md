# `virtual_env` — Virtual Environment Manager

[![Module](https://img.shields.io/badge/module-core-5c7cfa?style=flat-square)](https://github.com/polsoft-seb07uk)
[![Version](https://img.shields.io/badge/version-1.2-brightgreen?style=flat-square)](https://github.com/polsoft-seb07uk)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow?style=flat-square)](https://opensource.org/licenses/MIT)
[![Brand](https://img.shields.io/badge/polsoft.ITS%E2%84%A2-Group-9c27b0?style=flat-square)](mailto:polsoft.its@fastservice.com)

> **Core module of [TerminalX EcoSystem](https://github.com/polsoft-seb07uk)**  
> Manages a dedicated Python virtual environment inside the terminal — install, resolve, apply, sync — without leaving the prompt.

---

## Overview

`virtual_env` gives TerminalX its own isolated Python library space (`~/.crossterm/venv/lib`), independent of the system Python.  
Every library installed through `venv install` lands in that directory and is immediately available for import inside the running terminal session.

**Priority chain:**

```
ecosystem  →  ~/.crossterm/venv/lib  (highest priority)
os         →  system Python / PATH
auto       →  ecosystem first, then os fallback  (default)
```

The module integrates natively with the rest of the EcoSystem core:

| Integration point | What it does |
|---|---|
| `_integration` registry | Exposes a public API — other modules call `venv` without direct imports |
| `config` module | Reads and writes the `"venv"` section of `config.json` through the shared config writer — no read-modify-write races |
| `pkg` module | After every `pkg install pip <name>`, pkg calls `venv_register_installed()` so the venv index is immediately up to date |
| `notify` module | Sends desktop/system notifications on `install`, `uninstall`, and `sync` completion |

---

## Installation

`virtual_env` is a **core module** — it ships inside `core/` and loads automatically with TerminalX.  
No manual installation is required.

```
EcoSystem/
└── core/
    └── virtual_env.py   ← this module
```

Loading order in `core/__init__.py`:

```python
_LOAD_ORDER_FIRST = [
    ...
    "pkg",          # packages — must be before venv
    "virtual_env",  # loads after pkg, config, notify
    ...
]
```

---

## Commands

All commands are available via `venv`, `ve`, or `virtualenv`.

### Library management

```
venv install <lib>                   Install to EcoSystem (no deps)
venv install <lib> --with-deps       Install with all dependencies
venv uninstall <lib>                 Remove from EcoSystem
venv set <lib> ecosystem|os|auto     Override resolution source for a library
```

### Inspection

```
venv list                            Table: all libraries, sources, locations
venv status <lib>                    Detailed info: ecosystem vs OS, which wins
venv check                           Health-check: which libraries are missing
venv import <lib> [lib2 ...]         Live import test (not just metadata lookup)
```

### Path management

```
venv path                            Show all search paths
venv path add <path>                 Add custom path to the environment
venv path remove <path>              Remove a custom path
venv path clear                      Remove all custom paths
venv apply                           Apply EcoSystem paths to sys.path (current session)
venv autoload on|off                 Auto-apply paths on every terminal start
```

### Bulk operations

```
venv freeze [file]                   Export installed packages as requirements.txt
venv sync <requirements.txt>         Install all packages from a requirements file
venv sync <requirements.txt> --with-deps   Sync with dependencies
```

### Config & debug

```
venv export                          Export full config + installed list to JSON
venv reset                           Reset all settings to defaults (files untouched)
venv                                 Show this help menu
```

---

## Examples

```
# Install a library to the EcoSystem venv
venv install httpx

# Install with full dependency tree
venv install pillow --with-deps

# Check where a library comes from right now
venv status requests

# Force a specific library to always use the system Python
venv set pyinstaller os

# Bulk-install from a requirements file
venv sync requirements.txt

# Export installed libs to requirements.txt
venv freeze my_requirements.txt

# Enable auto-apply on terminal start
venv autoload on
```

---

## Integration API

Other core modules can use `virtual_env` without importing it directly.  
All calls go through `_integration`:

```python
from . import _integration

# Find a library (ecosystem → os, respects user config)
info, source = _integration.venv_find_library("requests")
# info: {"name": "requests", "version": "2.32.3", "location": "...", "dist_info": "..."}
# source: "ecosystem" | "os" | "os [fallback]" | "auto [nie znaleziono]"

# Apply EcoSystem paths to sys.path
added = _integration.venv_apply_paths()
# returns: number of newly added paths (int)

# Register a package installed externally (e.g. from pkg.py)
_integration.venv_register_installed("httpx", "0.27.0", "ecosystem")

# Check if the module is loaded
if _integration.venv_is_available():
    ...
```

### Registered API keys

| Key | Signature | Description |
|---|---|---|
| `find_in_ecosystem` | `(lib: str) → dict\|None` | Search only in `~/.crossterm/venv/lib` |
| `find_library` | `(lib: str) → (dict\|None, str)` | Full resolution with source priority |
| `get_venv_paths` | `() → list[str]` | All active search directories |
| `apply_paths` | `() → int` | Add venv paths to `sys.path`, return count |
| `register_installed` | `(name, version, source) → None` | Update config + invalidate cache |
| `is_autoload` | `() → bool` | Current autoload setting |
| `config_snapshot` | `() → dict` | Full state snapshot for diagnostics |
| `invalidate_cache` | `() → None` | Force re-scan of the dist-info index |

---

## Configuration

The module stores its state in the `"venv"` section of `~/.crossterm/config.json`:

```json
{
  "venv": {
    "library_sources": {
      "pillow": "ecosystem",
      "pyinstaller": "os"
    },
    "extra_paths": [
      "/home/user/my_libs"
    ],
    "autoload": false
  }
}
```

| Key | Type | Default | Description |
|---|---|---|---|
| `library_sources` | `dict[str, str]` | `{}` | Per-library source override |
| `extra_paths` | `list[str]` | `[]` | Additional search paths |
| `autoload` | `bool` | `false` | Apply paths automatically on terminal start |

> **Migration:** If a legacy `venv_config.json` is detected, it is read once and merged into `config.json` automatically on first save.

---

## Directory layout

```
~/.crossterm/
├── config.json          ← shared config (includes "venv" section)
└── venv/
    └── lib/
        ├── requests/
        │   └── __init__.py
        ├── requests-2.32.3.dist-info/
        │   ├── METADATA
        │   └── top_level.txt
        └── ...
```

Libraries are installed with `pip install --target ~/.crossterm/venv/lib`.  
Resolution uses `METADATA` and `top_level.txt` — no filename heuristics.

---

## How it works

### Library discovery

```
_EcosystemIndex
  └── scans *.dist-info in target_dir
      ├── reads METADATA  → name, version
      └── reads top_level.txt → resolves importable path
```

Results are cached per `target_dir` for the session lifetime.  
Cache is invalidated after every `install`, `uninstall`, `path add/remove`.

### Resolution flow

```
venv resolve "requests"
    │
    ├─ get_source("requests")  → "auto" (default)
    │
    ├─ _find_in_ecosystem("requests")  ✓ found
    │       └─ returns info dict + "ecosystem"
    │
    └─ (if not found) _find_in_os("requests")
            └─ importlib.metadata.distribution()  — no subprocess
```

---

## Changelog

### v1.2 — core integration *(current)*
- Moved from `modules/` to `core/` — loads as a full core module
- `_VenvConfig` writes through `_integration.call("config", "set_section", ...)` — eliminates R-M-W race
- `setup()` registers public API under `"venv"` key in `_integration`
- `pkg.py` calls `venv_register_installed()` after every successful pip install
- `notify` integration on install / uninstall / sync
- New `teardown()` — clean unregister from `_integration`

### v1.1
- New discovery engine based on `dist-info/METADATA` + `top_level.txt`
- `_EcosystemIndex` per target dir with lazy build and invalidation
- `_find_in_os` using `importlib.metadata` — no subprocess
- Session-level `_resolve_cache` with targeted invalidation
- `venv check`, `venv import`, `venv freeze`, `venv sync` commands

### v1.0
- Initial release: `venv list`, `venv install`, `venv set`, `venv path`, `venv apply`, `venv autoload`

---

## Author

**Sebastian Januchowski** — [polsoft.ITS™ Group](mailto:polsoft.its@fastservice.com)  
GitHub: [@polsoft-seb07uk](https://github.com/polsoft-seb07uk)  
License: MIT
