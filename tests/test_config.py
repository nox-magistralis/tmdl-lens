"""
test_config.py — pytest tests for src.config.
"""

from tmdl_lens.config import validate_config


def test_valid_config_no_warnings(tmp_path):
    warnings = validate_config({
        "reports_folder": str(tmp_path),
        "output_folder":  str(tmp_path),
        "watch_debounce": 10,
        "output_format":  "md",
    })
    assert warnings == []


def test_empty_reports_folder_warns():
    warnings = validate_config({"reports_folder": ""})
    assert any("reports_folder" in w for w in warnings)


def test_missing_reports_folder_warns(tmp_path):
    missing = str(tmp_path / "does-not-exist")
    warnings = validate_config({"reports_folder": missing})
    assert any("does not exist" in w for w in warnings)


def test_missing_output_folder_warns(tmp_path):
    warnings = validate_config({
        "reports_folder": str(tmp_path),
        "output_folder":  str(tmp_path / "does-not-exist"),
    })
    assert any("output_folder" in w for w in warnings)


def test_watch_debounce_out_of_range_warns():
    warnings = validate_config({"watch_debounce": 500})
    assert any("watch_debounce" in w for w in warnings)


def test_watch_debounce_non_numeric_warns():
    warnings = validate_config({"watch_debounce": "abc"})
    assert any("watch_debounce" in w for w in warnings)


def test_invalid_output_format_warns():
    warnings = validate_config({"output_format": "pdf"})
    assert any("output_format" in w for w in warnings)
