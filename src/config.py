"""
config.py — Config read/write for tmdl-lens.

Persists user settings to config.json in the same folder as the
running script or executable. All keys are optional — defaults are
applied for anything missing.
"""

import json
import os
import re
import sys


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULTS = {
    "reports_folder":   "",
    "output_folder":    "",
    "overwrite_readme": False,
    "include_dax":      True,
    "output_format":    "html",
    "skip_unchanged":   True,
    "watch_enabled":    True,
    "watch_debounce":   10,
    "schedule_enabled": False,
    "schedule_day":     "Mon",
    "schedule_time":    "08:00",
    "features": {
        "watcher": True,
    },
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
    config["features"] = dict(DEFAULTS["features"])
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            for k, v in saved.items():
                if k not in DEFAULTS:
                    continue
                if k == "features" and isinstance(v, dict):
                    config["features"] = {**DEFAULTS["features"], **v}
                else:
                    config[k] = v
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


def reset() -> bool:
    """
    Overwrite config.json on disk with the DEFAULTS values.
    Returns True on success, False on failure.
    """
    path = _config_path()
    config_to_save = dict(DEFAULTS)
    config_to_save["features"] = dict(DEFAULTS["features"])
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config_to_save, f, indent=2)
        return True
    except OSError:
        return False


def validate(config: dict) -> list[str]:
    errors = []
    if config.get("output_format") not in ("html", "md"):
        errors.append("output_format must be 'html' or 'md'")
    wd = config.get("watch_debounce")
    if not isinstance(wd, int) or wd < 1:
        errors.append("watch_debounce must be an integer >= 1")
    st = config.get("schedule_time")
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", str(st)):
        errors.append("schedule_time must match HH:MM format (24h)")
    sd = config.get("schedule_day")
    if sd not in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"):
        errors.append("schedule_day must be one of: Mon, Tue, Wed, Thu, Fri, Sat, Sun")
    rf = config.get("reports_folder")
    if rf and not isinstance(rf, str):
        errors.append("reports_folder must be a string")
    of = config.get("output_folder")
    if of and not isinstance(of, str):
        errors.append("output_folder must be a string")
    return errors


def config_path() -> str:
    """Returns the resolved config.json path (for display in UI)."""
    return _config_path()
