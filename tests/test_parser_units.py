"""Fragment-level tests for the TMDL parser text-processing functions."""

from tmdl_lens.tmdl_parser import (
    SourceExpression,
    _classify_m_content,
    _dedent,
    _extract_blocks,
    _extract_connector_details,
    _parse_calculation_items,
    _parse_tree,
    _strip_m_comments,
)


def test_strip_line_comments():
    content = "let\n    x = 1, // trailing comment\nin\n    x"
    result = _strip_m_comments(content)
    assert "comment" not in result
    assert "x = 1," in result


def test_strip_preserves_urls_in_strings():
    content = 'let\n    url = "https://example.com/api",\n    x = 1\nin\n    x'
    result = _strip_m_comments(content)
    assert "https://example.com/api" in result


def test_strip_block_comments():
    content = "let\n    /* multi\n       line */\n    x = 1\nin x"
    result = _strip_m_comments(content)
    assert "multi" not in result
    assert "x = 1" in result


def test_dedent_common_indent():
    assert _dedent("  line1\n    line2\n  line3") == "line1\n  line2\nline3"


def test_dedent_blank_lines():
    assert _dedent("\n  a\n\n  b\n") == "a\n\nb"


def test_dedent_empty():
    assert _dedent("") == ""


def test_extract_blocks_multiple():
    text = "table Sales\n\tdataType: int64\n\tisHidden\ntable Other\n\tdataType: string"
    blocks = _extract_blocks(text, "table ")
    assert len(blocks) == 2
    assert blocks[0].startswith("table Sales")
    assert "dataType: int64" in blocks[0]
    assert "table Other" not in blocks[0]


def test_extract_blocks_column_keyword():
    text = "table Sales\n\tcolumn 'A'\n\t\tdataType: int64\n\tcolumn 'B'\n\t\tisHidden"
    blocks = _extract_blocks(text, "column ")
    assert len(blocks) == 2
    assert "'A'" in blocks[0]
    assert "'B'" in blocks[1]
    assert "dataType: int64" in blocks[0]


def test_parse_tree_flat_properties():
    lines = ["table Sales", "\tdataType: int64", "\tisHidden"]
    nodes, next_i = _parse_tree(lines, 1, 0)
    assert len(nodes) == 2
    assert nodes[0].key == "dataType"
    assert nodes[0].value == "int64"
    assert nodes[1].key == "isHidden"
    assert nodes[1].value == ""
    assert next_i == 3


def test_parse_tree_nested_children():
    lines = ["table Sales", "\tcolumns", "\t\tcol A", "\t\tcol B", "\tmeasures", "\t\tm1"]
    nodes, next_i = _parse_tree(lines, 1, 0)
    assert len(nodes) == 2
    assert [c.key for c in nodes[0].children] == ["col A", "col B"]
    assert [c.key for c in nodes[1].children] == ["m1"]


def test_parse_tree_backtick_value():
    lines = ["table Sales", "\texpression = ```", "\t\tSUM(1)", "\t```", "\tdataType: int64"]
    nodes, next_i = _parse_tree(lines, 1, 0)
    assert nodes[0].key == "expression"
    assert nodes[0].value == "SUM(1)"
    assert nodes[1].key == "dataType"


def test_classify_scalar_helper():
    expr = _classify_m_content("let x = 1 in x", "t", result_type="Number")
    assert expr.source_type == "scalar_helper"


def test_classify_table_combine():
    expr = _classify_m_content('let s = Table.Combine({#"a", #"b"}) in s', "t")
    assert expr.source_type == "table_combine"
    assert expr.combine_sources == ["a", "b"]


def test_classify_hardcoded():
    expr = _classify_m_content('#table({"a", "b"}, {1, 2})', "t")
    assert expr.source_type == "hardcoded"


def test_classify_embedded():
    expr = _classify_m_content("Table.FromRows({1, 2})", "t")
    assert expr.source_type == "embedded"


def test_classify_sql_connector():
    expr = _classify_m_content('let src = Sql.Database("srv", "db") in src', "t")
    assert expr.source_type == "connector"
    assert expr.connector_namespace == "Sql"
    assert expr.connector_function == "Database"
    assert expr.server == "srv"
    assert expr.database == "db"


def test_classify_ignores_m_stdlib():
    expr = _classify_m_content("let t = Table.SelectRows(x, each true) in t", "t")
    assert expr.source_type != "connector"


def test_classify_derived_quoted():
    expr = _classify_m_content('let Source = #"source-sql-direct" in Source', "t")
    assert expr.source_type == "derived"
    assert expr.derived_from == "source-sql-direct"


def test_classify_derived_bare_table():
    expr = _classify_m_content("let\n    Source = myTable\nin\n    Source", "t")
    assert expr.source_type == "derived_table"
    assert expr.derived_from == "myTable"


def test_classify_unresolved():
    expr = _classify_m_content("let x = SomeUnknownThing(y) in x", "t")
    assert expr.source_type == "unknown"


def test_connector_details_sql_native_query():
    expr = SourceExpression(
        name="t", source_type="connector",
        connector_namespace="Sql", connector_function="Database",
    )
    _extract_connector_details(
        expr, 'Sql.Database("srv", "db", [Query = "select 1"])', "Sql", "Database"
    )
    assert expr.server == "srv"
    assert expr.database == "db"
    assert expr.is_native_query is True
    assert expr.native_query == "select 1"


def test_connector_details_dataflow():
    expr = SourceExpression(
        name="t", source_type="connector",
        connector_namespace="PowerBI", connector_function="Dataflows",
    )
    _extract_connector_details(
        expr,
        'PowerBI.Dataflows(workspaceId = "ws", dataflowId = "df", entity = "e")',
        "PowerBI", "Dataflows",
    )
    assert expr.workspace_id == "ws"
    assert expr.dataflow_id == "df"
    assert expr.entity == "e"


def test_connector_details_odbc():
    expr = SourceExpression(
        name="t", source_type="connector",
        connector_namespace="Odbc", connector_function="DataSource",
    )
    _extract_connector_details(expr, 'Odbc.DataSource("dsn=MyDSN")', "Odbc", "DataSource")
    assert expr.dsn == "dsn=MyDSN"


def test_connector_details_navigation_fallback():
    expr = SourceExpression(
        name="t", source_type="connector",
        connector_namespace="Something", connector_function="Else",
    )
    _extract_connector_details(expr, '{[Schema = "dbo", Item = "orders"]}[Data]', "Something", "Else")
    assert len(expr.physical_tables) == 1
    assert expr.physical_tables[0].schema == "dbo"
    assert expr.physical_tables[0].table == "orders"
    assert expr.physical_tables[0].source == "navigation"


def test_calc_items_inline_fenced_expression():
    content = (
        "table 'Time Intelligence'\n"
        "\tcalculationGroup\n"
        "\n"
        "\t\tcalculationItem MTD = ```\n"
        "\t\t\tCALCULATE(\n"
        "\t\t\t\tSELECTEDMEASURE(),\n"
        "\t\t\t\tDATESMTD('Date'[date])\n"
        "\t\t\t)\n"
        "\t\t\t```\n"
        "\n"
        "\t\tcalculationItem 'Rolling 12M' = ```\n"
        "\t\t\tDIVIDE(\n"
        "\t\t\t\tSELECTEDMEASURE() - CALCULATE(SELECTEDMEASURE(), SAMEPERIODLASTYEAR('Date'[date])),\n"
        "\t\t\t\tCALCULATE(SELECTEDMEASURE(), SAMEPERIODLASTYEAR('Date'[date]))\n"
        "\t\t\t)\n"
        "\t\t\t```\n"
    )
    items = _parse_calculation_items(content)
    assert [it.name for it in items] == ["MTD", "Rolling 12M"]
    mtd = items[0]
    assert mtd.ordinal == 0
    assert mtd.dax_expression.startswith("CALCULATE(")
    assert "DATESMTD('Date'[date])" in mtd.dax_expression
    assert mtd.format_string_expression == ""
    assert "SAMEPERIODLASTYEAR" in items[1].dax_expression


def test_calc_items_property_style():
    content = (
        "table 'Time Intelligence'\n"
        "\tcalculationGroup\n"
        "\t\tcalculationItem 'Rolling 12M'\n"
        "\t\t\tordinal: 2\n"
        "\t\t\texpression = ```\n"
        "\t\t\t\tCALCULATE(SELECTEDMEASURE(), DATESINPERIOD('Date'[date], LASTDATE('Date'[date]), -12, MONTH))\n"
        "\t\t\t\t```\n"
        "\t\t\tformatStringExpression = \"0.00%\"\n"
    )
    items = _parse_calculation_items(content)
    assert len(items) == 1
    it = items[0]
    assert it.name == "Rolling 12M"
    assert it.ordinal == 2
    assert "DATESINPERIOD" in it.dax_expression
    assert it.format_string_expression == "0.00%"


def test_calc_items_inline_with_ordinal_and_format_children():
    content = (
        "table 'Time Intelligence'\n"
        "\tcalculationGroup\n"
        "\t\tcalculationItem MTD = ```\n"
        "\t\t\tCALCULATE(SELECTEDMEASURE(), DATESMTD('Date'[date]))\n"
        "\t\t\t```\n"
        "\t\t\tordinal: 3\n"
        "\t\t\tformatStringExpression = ```\n"
        "\t\t\t\tSELECTEDMEASUREFORMATSTRING()\n"
        "\t\t\t\t```\n"
    )
    items = _parse_calculation_items(content)
    assert len(items) == 1
    it = items[0]
    assert it.ordinal == 3
    assert "DATESMTD" in it.dax_expression
    assert it.format_string_expression == "SELECTEDMEASUREFORMATSTRING()"
