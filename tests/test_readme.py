"""
test_readme.py - pytest tests for the Markdown/HTML generators.
"""

from tmdl_lens.readme_generator import generate_html, generate_readme


def test_readme_title(sample_model, sample_resolved, gen_config):
    readme = generate_readme(sample_model, sample_resolved, gen_config)
    assert readme.startswith("# tmdl-lens Test Report")


def test_readme_sections(sample_model, sample_resolved, gen_config):
    readme = generate_readme(sample_model, sample_resolved, gen_config)
    for heading in [
        "## Overview",
        "## 1. Data Sources",
        "## 2. Table Details",
        "## 3. Measures",
        "## 4. Relationships",
        "## 5. Security Roles",
        "## 6. M Parameters",
        "## 7. Model Statistics",
    ]:
        assert heading in readme


def test_readme_unresolved_section(sample_model, sample_resolved, gen_config):
    readme = generate_readme(sample_model, sample_resolved, gen_config)
    assert "## ⚠ Unresolved Sources" in readme


def test_readme_includes_metadata(sample_model, sample_resolved, gen_config):
    readme = generate_readme(sample_model, sample_resolved, gen_config)
    assert "Report Owner" in readme
    assert "BI Team" in readme
    assert "Daily at 06:00 UTC" in readme


def test_readme_omits_blank_metadata(sample_model, sample_resolved):
    config = {
        "report_name":      "tmdl-lens Test Report",
        "owner":            "",
        "team":             "",
        "refresh_schedule": "",
        "include_dax":      True,
    }
    readme = generate_readme(sample_model, sample_resolved, config)
    assert "Owner" not in readme
    assert "Team" not in readme
    assert "Refresh Schedule" not in readme


def test_readme_dax_optional(sample_model, sample_resolved, gen_config):
    without_dax = generate_readme(
        sample_model, sample_resolved, {**gen_config, "include_dax": False}
    )
    with_dax = generate_readme(sample_model, sample_resolved, gen_config)
    assert len(with_dax) > len(without_dax)


def test_html_generation(sample_model, sample_resolved, gen_config):
    html = generate_html(sample_model, sample_resolved, gen_config)
    assert html.startswith("<!DOCTYPE html>")
    assert "tmdl-lens Test Report" in html
    assert "<h2>1. Data Sources</h2>" in html
    assert "<h2>7. Model Statistics</h2>" in html
