"""Fragment-level tests for the source resolver helpers."""

from tmdl_lens.source_resolver import (
    _build_chain_label,
    _build_label,
    _copy_resolved,
    _from_expr,
    _resolve_param,
    _terminal_label,
    _unresolved,
    get_table_source,
    list_unresolved,
    resolve_sources,
)
from tmdl_lens.tmdl_parser import SourceExpression, Table, _classify_m_content


def test_label_native_query_sql():
    expr = SourceExpression(
        name="t", source_type="connector",
        connector_namespace="Sql", connector_function="Database",
        is_native_query=True, server="srv", database="db",
    )
    assert _build_label(expr, {}) == "SQL (native query) -> srv -> db"


def test_label_sql_with_table():
    expr = SourceExpression(
        name="t", source_type="connector",
        connector_namespace="Sql", connector_function="Database",
        server="srv", database="db", schema="dbo", table_or_view="orders",
    )
    assert _build_label(expr, {}) == "SQL -> srv -> db -> dbo.orders"


def test_label_parameter_resolution():
    expr = SourceExpression(
        name="t", source_type="connector",
        connector_namespace="Sql", connector_function="Database",
        server="[param:ServerName]", database="[param:DatabaseName]",
    )
    label = _build_label(expr, {"ServerName": "prod-server", "DatabaseName": "SalesDB"})
    assert label == "SQL -> prod-server -> SalesDB"


def test_label_unknown_connector_generic():
    expr = SourceExpression(
        name="t", source_type="connector",
        connector_namespace="CloudMart", connector_function="Warehouses",
    )
    assert _build_label(expr, {}) == "CloudMart -> Warehouses"


def test_label_unknown_connector_with_detail():
    expr = SourceExpression(
        name="t", source_type="connector",
        connector_namespace="CloudMart", connector_function="Warehouses",
        url="https://x",
    )
    assert _build_label(expr, {}) == "CloudMart -> Warehouses -> https://x"


def test_label_non_connector_types():
    assert _build_label(SourceExpression(name="t", source_type="hardcoded"), {}) == "Hardcoded (inline M)"
    assert _build_label(SourceExpression(name="t", source_type="embedded"), {}) == "Embedded data"
    assert _build_label(
        SourceExpression(name="t", source_type="table_combine", combine_sources=["a", "b"]), {}
    ) == "Combines: a, b"
    assert _build_label(SourceExpression(name="t", source_type="scalar_helper"), {}) == "Scalar Helper"
    assert _build_label(SourceExpression(name="t", source_type="function_def"), {}) == "Function Def"


def test_resolve_param_substitutes():
    assert _resolve_param("[param:ServerName]", {"ServerName": "srv"}) == "srv"


def test_resolve_param_unknown_keeps_marker():
    assert _resolve_param("[param:Missing]", {"ServerName": "srv"}) == "[param:Missing]"


def test_resolve_param_plain_passthrough():
    assert _resolve_param("literal", {}) == "literal"


def test_build_chain_label():
    assert _build_chain_label(["parent"], "SQL -> srv") == "parent -> SQL -> srv"
    assert _build_chain_label([], "SQL -> srv") == "SQL -> srv"


def test_terminal_label():
    rs = _from_expr(SourceExpression(name="t", source_type="hardcoded"), {}, tier=1)
    assert _terminal_label(rs) == "Hardcoded (inline M)"


def test_from_expr_builds_resolved():
    expr = SourceExpression(
        name="q", source_type="connector",
        connector_namespace="Sql", connector_function="Database",
        server="[param:ServerName]", database="db",
    )
    rs = _from_expr(expr, {"ServerName": "srv"}, tier=1)
    assert rs.expression_name == "q"
    assert rs.resolution_tier == 1
    assert rs.server == "srv"
    assert rs.label == "SQL -> srv -> db"


def test_copy_resolved_preserves_details():
    parent = _from_expr(
        SourceExpression(
            name="p", source_type="connector",
            connector_namespace="Sql", connector_function="Database",
            server="srv", database="db",
        ),
        {}, tier=1,
    )
    rs = _copy_resolved("child", parent, tier=2)
    assert rs.expression_name == "child"
    assert rs.resolution_tier == 2
    assert rs.server == "srv"
    assert rs.database == "db"
    assert rs.label == parent.label


def test_unresolved_marker():
    rs = _unresolved("q", "no such source")
    assert rs.unresolved is True
    assert rs.resolution_tier == 3
    assert rs.source_type == "unresolved"
    assert rs.unresolved_reason == "no such source"
    assert rs.label == "Unresolved - no such source"


def test_get_table_source_by_ref():
    resolved = {"q": _unresolved("q", "x")}
    table = Table(name="t", table_type="fact", source_ref="q")
    assert get_table_source(table, resolved) is resolved["q"]


def test_get_table_source_none():
    table = Table(name="t", table_type="fact")
    assert get_table_source(table, {}) is None


def test_list_unresolved():
    resolved = {
        "a": _unresolved("a", "x"),
        "b": _from_expr(SourceExpression(name="b", source_type="hardcoded"), {}, tier=1),
    }
    names = [rs.expression_name for rs in list_unresolved(resolved)]
    assert names == ["a"]

def test_resolve_expression_referencing_inline_table():
    dose_log = Table(
        name="dose-log",
        table_type="fact",
        partition_type="m",
        inline_source=_classify_m_content(
            'let\n'
            '    Source = SharePoint.Files("https://contoso.sharepoint.com/sites/dose")\n'
            'in\n'
            '    Source',
            "dose-log",
        ),
    )
    per_dose = _classify_m_content(
        'let\n'
        '    Source = #"dose-log"\n'
        'in\n'
        '    Source',
        "dose-log-per-dose-source",
    )
    resolved = resolve_sources([per_dose], [], tables=[dose_log])
    rs = resolved["dose-log-per-dose-source"]
    assert rs.unresolved is False
    assert rs.derived_from == "dose-log"
    assert rs.chain[0] == "dose-log"
    assert rs.sharepoint_url == "https://contoso.sharepoint.com/sites/dose"


def test_resolve_inline_alias_from_parser():
    shared = SourceExpression(
        name="cmo-mapping-source",
        source_type="connector",
        connector_namespace="SharePoint",
        connector_function="Files",
        sharepoint_url="https://contoso.sharepoint.com/sites/dose",
    )
    cmo = Table(
        name="cmo_capacity",
        table_type="fact",
        partition_type="m",
        inline_source=_classify_m_content(
            'let\n'
            '    wb = #"cmo-mapping-source"\n'
            'in\n'
            '    wb',
            "cmo_capacity",
        ),
    )
    resolved = resolve_sources([shared], [], tables=[cmo])
    rs = resolved["cmo_capacity"]
    assert rs.unresolved is False
    assert rs.derived_from == "cmo-mapping-source"
    assert rs.connector_namespace == "SharePoint"


def test_resolve_inline_reference_to_source_ref_table():
    direct = SourceExpression(
        name="source-sql-direct",
        source_type="connector",
        connector_namespace="Sql",
        connector_function="Database",
        server="srv",
        database="db",
        schema="dbo",
        table_or_view="orders",
    )
    alias_tbl = Table(
        name="dose-log",
        table_type="fact",
        partition_type="m",
        source_ref="source-sql-direct",
    )
    dep_tbl = Table(
        name="dose-log-per-dose",
        table_type="fact",
        partition_type="m",
        inline_source=_classify_m_content(
            'let\n'
            '    Source = #"dose-log"\n'
            'in\n'
            '    Source',
            "dose-log-per-dose",
        ),
    )
    resolved = resolve_sources([direct], [], tables=[alias_tbl, dep_tbl])
    rs = resolved["dose-log-per-dose"]
    assert rs.unresolved is False
    assert rs.derived_from == "dose-log"
    assert rs.server == "srv"


def test_resolve_expression_referencing_missing_target():
    expr = _classify_m_content(
        'let\n'
        '    Source = #"ghost"\n'
        'in\n'
        '    Source',
        "x",
    )
    resolved = resolve_sources([expr], [], tables=[])
    rs = resolved["x"]
    assert rs.unresolved is True
    assert "ghost" in rs.unresolved_reason
