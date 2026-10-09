"""
test_readme.py - pytest tests for the Markdown/HTML generators.
"""

from tmdl_lens.readme_generator import (
    _build_function_usage_map,
    _esc,
    generate_html,
    generate_readme,
)
from tmdl_lens.tmdl_parser import (
    Measure,
    SecurityRole,
    SemanticModel,
    Table,
    TableFilter,
    UserFunction,
)


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
        "## 4. Functions",
        "## 5. Relationships",
        "## 6. Security Roles",
        "## 7. M Parameters",
        "## 8. Model Statistics",
    ]:
        assert heading in readme


def test_readme_functions_section(sample_model, sample_resolved, gen_config):
    readme = generate_readme(sample_model, sample_resolved, gen_config)
    assert "## 4. Functions" in readme
    assert "`AddTax`" in readme
    assert "`SafeStockThreshold`" in readme
    assert "Adds sales tax to a net amount using the given rate." in readme
    assert "Returns the reorder threshold for a product category." in readme
    assert "```dax" in readme
    assert "(amount: number, rate: number) => amount * (1 + rate)" in readme


def test_function_usage_map():
    fn = UserFunction(name="AddTax", expression="x")
    quoted_fn = UserFunction(name="My Func", expression="x")
    other = UserFunction(name="Unused", expression="x")
    measures = [
        Measure(name="Taxed", dax_expression="AddTax([Total], 0.23)"),
        Measure(name="Quoted Call", dax_expression="'My Func'([x]) + AddTax([y], 0.1)"),
        Measure(name="Plain", dax_expression="SUM('fact-sales'[amount])"),
    ]
    table = Table(name="_measures", table_type="measures_only", measures=measures)
    model = SemanticModel(report_name="T", tables=[table], functions=[fn, quoted_fn, other])
    usage = _build_function_usage_map(model)
    assert usage["AddTax"] == [("Taxed", "_measures"), ("Quoted Call", "_measures")]
    assert usage["My Func"] == [("Quoted Call", "_measures")]
    assert "Unused" not in usage


def test_esc_is_idempotent():
    once = _esc("a&b<c>d\"e")
    assert _esc(once) == once


def test_html_escapes_once():
    fn = UserFunction(name="Tax Calc", expression="x", description="R&D <Ops> \"q\"")
    measure = Measure(name="Taxed", dax_expression="AddTax([Total], 0.23)", description="R&D <Ops>")
    table = Table(name="_measures", table_type="measures_only", measures=[measure])
    model = SemanticModel(report_name="T", tables=[table], functions=[fn])
    html = generate_html(model, {}, {"report_name": "T", "include_dax": True})
    assert "R&amp;D &lt;Ops&gt;" in html
    assert "R&amp;amp;D" not in html
    assert "&amp;lt;" not in html
    assert "R&amp;D &lt;Ops&gt; &quot;q&quot;" in html


def test_html_role_dynamic_label_escaped_once():
    role = SecurityRole(
        name="R& D",
        table_filters=[TableFilter(table="t", dax_filter="[a] = \"x\"")],
        is_dynamic=True,
        dynamic_function="USER&NAME",
    )
    model = SemanticModel(report_name="T", tables=[], security_roles=[role])
    html = generate_html(model, {}, {"report_name": "T", "include_dax": True})
    assert "Yes (USER&amp;NAME)" in html
    assert "Yes (USER&amp;amp;NAME)" not in html


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
    assert "<h2>8. Model Statistics</h2>" in html


def test_generation_is_deterministic(sample_model, sample_resolved, gen_config):
    first_md = generate_readme(sample_model, sample_resolved, gen_config)
    second_md = generate_readme(sample_model, sample_resolved, gen_config)
    first_html = generate_html(sample_model, sample_resolved, gen_config)
    second_html = generate_html(sample_model, sample_resolved, gen_config)
    assert first_md.encode("utf-8") == second_md.encode("utf-8")
    assert first_html.encode("utf-8") == second_html.encode("utf-8")
