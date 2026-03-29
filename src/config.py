"""
config.py — Config read/write for tmdl-lens.

Persists user settings to config.json in the same folder as the
running script or executable. All keys are optional — defaults are
applied for anything missing.
"""

import json
import os
import sys


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULTS = {
    "reports_folder":   "",
    "output_folder":    "",
    "overwrite_readme": False,
    "include_dax":      True,
    "skip_unchanged":   True,
    "watch_enabled":    True,
    "watch_debounce":   10,
    "schedule_enabled": False,
    "schedule_day":     "Mon",
    "schedule_time":    "08:00",
}


# ---------------------------------------------------------------------------
# Location
# ---------------------------------------------------------------------------

def _config_path() -> str:
    """
    Returns the path to config.json.
    - When running as a PyInstaller .exe: same folder as the .exe
    - When running as a .py script: parent of src/ (i.e. repo root / main.py folder)
    """
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        # __file__ is src/config.py — go up one level to reach repo root
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "config.json")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load() -> dict:
    """Load config from disk, merging with defaults for any missing keys."""
    path = _config_path()
    config = dict(DEFAULTS)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            config.update({k: v for k, v in saved.items() if k in DEFAULTS})
        except (json.JSONDecodeError, OSError):
            pass
    return config


def save(config: dict) -> bool:
    """
    Save config to disk.
    Returns True on success, False on failure.
    """
    path = _config_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        return True
    except OSError:
        return False


def config_path() -> str:
    """Returns the resolved config.json path (for display in UI)."""
    return _config_path()
