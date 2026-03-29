"""
workspace_config.py — Read/write tmdl-lens.json from the reports folder.

This file stores report-level settings: who owns the reports, what team,
refresh schedule, and per-report overrides. It lives inside the reports
folder so it travels with the data, not with the program.

Separate from config.json which handles program/UI preferences.
"""

import json
import os


FILENAME = "tmdl-lens.json"

DEFAULTS = {
    "owner":            "",
    "team":             "",
    "refresh_schedule": "",
    "reports":          {},
}

# Keys allowed at the top level and inside per-report overrides.
# Used during validation to catch wrong files or hand-edited mistakes.
_TOP_LEVEL_KEYS    = {"owner", "team", "refresh_schedule", "reports"}
_PER_REPORT_KEYS   = {"owner", "team", "refresh_schedule"}


def path(folder: str) -> str:
    return os.path.join(folder, FILENAME)


def validate(data: dict) -> tuple[bool, str]:
    """
    Returns (True, "") if the data looks usable.
    Returns (False, reason) if something is wrong.
    """
    if not isinstance(data, dict):
        return False, "file root is not a JSON object"

    unknown = set(data.keys()) - _TOP_LEVEL_KEYS
    if unknown:
        return False, f"unexpected keys: {', '.join(sorted(unknown))}"

    reports = data.get("reports", {})
    if not isinstance(reports, dict):
        return False, "'reports' must be a JSON object, not a list or string"

    for report_name, overrides in reports.items():
        if not isinstance(overrides, dict):
            return False, f"overrides for '{report_name}' must be a JSON object"
        unknown_override = set(overrides.keys()) - _PER_REPORT_KEYS
        if unknown_override:
            return False, f"unknown override keys for '{report_name}': {', '.join(sorted(unknown_override))}"

    return True, ""


def load(folder: str) -> tuple[dict, str]:
    """
    Load tmdl-lens.json from the given folder.

    Returns (config_dict, error_message).
    - On success: (merged_config, "")
    - File missing: creates it with defaults, returns (defaults, "")
    - Parse or validation error: returns (defaults, error_message)
    """
    p = path(folder)

    if not os.path.exists(p):
        defaults = dict(DEFAULTS)
        defaults["reports"] = {}
        _write(p, defaults)
        return defaults, ""

    try:
        with open(p, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except json.JSONDecodeError as e:
        return dict(DEFAULTS), f"JSON parse error: {e}"
    except OSError as e:
        return dict(DEFAULTS), f"could not read file: {e}"

    ok, reason = validate(raw)
    if not ok:
        return dict(DEFAULTS), f"validation failed: {reason}"

    # Merge with defaults so missing keys don't cause KeyErrors later
    config = dict(DEFAULTS)
    config.update({k: v for k, v in raw.items() if k in _TOP_LEVEL_KEYS})
    if "reports" not in config or not isinstance(config["reports"], dict):
        config["reports"] = {}

    return config, ""


def save(folder: str, data: dict) -> tuple[bool, str]:
    """
    Write data to tmdl-lens.json in the given folder.
    Returns (True, "") on success, (False, error) on failure.
    """
    p = path(folder)
    try:
        _write(p, data)
        return True, ""
    except OSError as e:
        return False, str(e)


def merge_report(ws_config: dict, report_name: str) -> dict:
    """
    Return a config dict for one report: workspace defaults with any
    per-report overrides applied on top.

    report_name should be the .pbip filename without extension.
    """
    merged = {
        "owner":            ws_config.get("owner", ""),
        "team":             ws_config.get("team", ""),
        "refresh_schedule": ws_config.get("refresh_schedule", ""),
    }
    overrides = ws_config.get("reports", {}).get(report_name, {})
    merged.update({k: v for k, v in overrides.items() if k in _PER_REPORT_KEYS})
    return merged


def _write(p: str, data: dict) -> None:
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
