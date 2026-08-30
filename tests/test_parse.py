"""
test_parse.py — pytest tests for tmdl_parser and source_resolver.

Run from the repo root:  python -m pytest
"""


def test_report_name(sample_model):
    assert sample_model.report_name == "tmdl-lens Test Report"


def test_tables_count(sample_model):
    assert len(sample_model.tables) == 8


def test_table_names(sample_model):
    names = sorted(t.name for t in sample_model.tables)
    assert names == [
        "_measures",
        "cg-time-intelligence",
        "dim-date",
        "dim-product",
        "fact-sales",
        "helper-order-lookup",
        "param-metric-selector",
        "source-sql-staging",
    ]


def test_table_classification(sample_model):
    types = {t.name: t.table_type for t in sample_model.tables}
    assert types == {
        "_measures":             "measures_only",
        "cg-time-intelligence":  "calc_group",
        "dim-date":              "calculated",
        "dim-product":           "dim",
        "fact-sales":            "fact",
        "helper-order-lookup":   "helper",
        "param-metric-selector": "field_parameter",
        "source-sql-staging":    "staging",
    }


def test_hidden_and_not_loaded_tables(sample_model):
    helper = next(t for t in sample_model.tables if t.name == "helper-order-lookup")
    assert helper.is_hidden is True
    staging = next(t for t in sample_model.tables if t.name == "source-sql-staging")
    assert staging.is_loaded is False


def test_m_parameters(sample_model):
    assert len(sample_model.m_parameters) == 2
    by_name = {p.name: p for p in sample_model.m_parameters}
    assert by_name["ServerName"].value == "fake-server.database.windows.net"
    assert by_name["DatabaseName"].value == "SalesDB"


def test_source_expressions(sample_model):
    assert len(sample_model.source_expressions) == 21


def test_relationships(sample_model):
    assert len(sample_model.relationships) == 3
    pairs = {
        (r.from_table, r.from_column, r.to_table, r.to_column)
        for r in sample_model.relationships
    }
    assert ("fact-sales", "order_date", "dim-date", "Date") in pairs
    assert ("fact-sales", "customer_id", "dim-product", "product_id") in pairs
    assert ("fact-sales", "ship_date", "dim-date", "Date") in pairs
    assert sum(1 for r in sample_model.relationships if not r.is_active) == 1


def test_measures(sample_model):
    by_table = {t.name: t.measures for t in sample_model.tables}
    assert len(by_table["_measures"]) == 4
    assert len(by_table["fact-sales"]) == 2
    assert len(by_table["helper-order-lookup"]) == 1
    names = {m.name for m in by_table["_measures"]}
    assert names == {
        "Total Sales Amount",
        "Order Count",
        "Avg Order Value",
        "Sales YTD",
    }


def test_resolved_sources_tiers(sample_resolved):
    assert len(sample_resolved) == 21
    tier1 = sum(1 for rs in sample_resolved.values() if rs.resolution_tier == 1)
    tier2 = sum(1 for rs in sample_resolved.values() if rs.resolution_tier == 2)
    tier3 = sum(1 for rs in sample_resolved.values() if rs.resolution_tier == 3)
    assert tier1 == 18
    assert tier2 == 1
    assert tier3 == 2


def test_resolved_sql_source(sample_resolved):
    rs = sample_resolved["source-sql-direct"]
    assert rs.source_type == "connector"
    assert rs.resolution_tier == 1
    assert "SalesDB" in rs.label
    assert "dbo.orders" in rs.label


def test_resolved_derived_chain(sample_resolved):
    rs = sample_resolved["source-derived"]
    assert rs.resolution_tier == 2
    assert rs.derived_from == "source-sql-direct"
    assert rs.chain[0] == "source-sql-direct"


def test_tier3_are_unresolved(sample_resolved):
    tier3 = [rs for rs in sample_resolved.values() if rs.resolution_tier == 3]
    assert len(tier3) == 2
    assert all(rs.unresolved for rs in tier3)
    names = sorted(rs.expression_name for rs in tier3)
    assert names == ["source-dynamic", "source-via-custom-function"]


def test_security_roles(sample_model):
    assert len(sample_model.security_roles) == 5
    names = {r.name for r in sample_model.security_roles}
    assert names == {
        "Regional Managers",
        "Employees",
        "Legacy Users",
        "Area Supervisors",
        "Administrators",
    }
    dynamic = {
        r.name: r.dynamic_function
        for r in sample_model.security_roles
        if r.is_dynamic
    }
    assert dynamic == {
        "Employees":   "USERPRINCIPALNAME",
        "Legacy Users": "USERNAME",
    }
    admins = next(r for r in sample_model.security_roles if r.name == "Administrators")
    assert admins.table_filters == []


def test_calculation_groups(sample_model):
    cgs = [t for t in sample_model.tables if t.table_type == "calc_group"]
    assert len(cgs) == 1
    cg = cgs[0]
    assert cg.name == "cg-time-intelligence"
    assert len(cg.calculation_items) == 5
    assert [i.name for i in cg.calculation_items] == [
        "YTD", "MTD", "Rolling 12M", "Prior Year", "YoY %",
    ]
    ytd = cg.calculation_items[0]
    assert "TOTALYTD" in ytd.dax_expression
    assert ytd.format_string_expression == "SELECTEDMEASUREFORMATSTRING()"
