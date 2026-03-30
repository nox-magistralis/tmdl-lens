"""
tmdl_parser.py — Core TMDL semantic model parser for tmdl-lens.

Parses the /definition folder of a Power BI SemanticModel and produces
a SemanticModel dataclass containing tables, relationships, measures,
and raw source expressions ready for resolution.
"""

import os
import re
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Column:
    name: str
    data_type: str
    is_calculated: bool = False
    dax_expression: str = ""
    is_hidden: bool = False


@dataclass
class Measure:
    name: str
    dax_expression: str
    display_folder: str = ""
    format_string: str = ""
    description: str = ""


@dataclass
class Relationship:
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    cardinality: str = ""
    is_active: bool = True


@dataclass
class TableFilter:
    table: str
    dax_filter: str


@dataclass
class SecurityRole:
    name: str
    table_filters: list = field(default_factory=list)
    is_dynamic: bool = False
    dynamic_function: str = ""  # "USERPRINCIPALNAME" | "USERNAME" | ""


@dataclass
class CalculationItem:
    name: str
    ordinal: int = 0
    dax_expression: str = ""
    format_string_expression: str = ""


@dataclass
class MParameter:
    """An M query parameter (IsParameterQuery = true)."""
    name: str
    value: str
    param_type: str = "Text"


@dataclass
class SourceExpression:
    """
    One entry from expressions.tmdl — a shared M query or M parameter.
    Also used for inline M sources classified directly from table files.

    source_type values:
      dataflow_pbi        PowerBI.Dataflows()
      dataflow_platform   PowerPlatform.Dataflows()
      sql                 Sql.Database()
      sql_native_query    Sql.Database() with native query
      odbc                Odbc.DataSource()
      sharepoint_files    SharePoint.Files()
      sharepoint_tables   SharePoint.Tables()
      excel_sharepoint    Excel.Workbook() via SharePoint.Files()
      excel_local         Excel.Workbook(File.Contents(...))
      csv_local           Csv.Document(File.Contents(...))
      web_api             Web.Contents()
      odata               OData.Feed()
      hardcoded           #table(...) inline data
      embedded            Table.FromRows() hardcoded data
      smartsheet          SmartsheetGlobal.Contents() or Smartsheet.Tables()
      table_combine       Table.Combine({...}) — union of queries
      calc_series         GENERATESERIES(...)
      connector_unknown   Unrecognised Namespace.Function() connector
      derived             references another expression via Source = #"name"
      derived_table       references another table inline
      parameter           IsParameterQuery = true
      function_def        function definition
      scalar_helper       returns a scalar value, not a table
      unknown             could not be classified
    """
    name: str
    source_type: str = "unknown"
    query_group: str = ""
    raw_m: str = ""

    # Dataflow fields
    workspace_id: str = ""
    dataflow_id: str = ""
    entity: str = ""

    # SQL fields
    server: str = ""
    database: str = ""
    schema: str = ""
    table_or_view: str = ""
    native_query: str = ""

    # ODBC fields
    dsn: str = ""

    # SharePoint / Excel / CSV fields
    sharepoint_url: str = ""
    file_name: str = ""
    sheet_name: str = ""

    # Web / OData fields
    url: str = ""

    # Derived / combine fields
    derived_from: str = ""
    combine_sources: list = field(default_factory=list)

    # Unknown connector — raw function name surfaced for user labelling
    connector_fn: str = ""

    # Custom function / parameter fields
    function_name: str = ""
    function_args: str = ""
    param_value: str = ""
    param_type: str = ""


@dataclass
class Table:
    name: str
    table_type: str
    query_group: str = ""
    partition_type: str = ""
    source_ref: str = ""
    is_hidden: bool = False
    is_loaded: bool = True
    columns: list = field(default_factory=list)
    measures: list = field(default_factory=list)
    calculation_items: list = field(default_factory=list)
    dax_partition: str = ""
    inline_source: Optional["SourceExpression"] = None


@dataclass
class SemanticModel:
    report_name: str
    tables: list = field(default_factory=list)
    relationships: list = field(default_factory=list)
    source_expressions: list = field(default_factory=list)
    m_parameters: list = field(default_factory=list)
    security_roles: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Connector signature registry
#
# Maps the start of a Power Query connector function call to a source_type.
# Checked in priority order — more specific patterns listed first.
# To add a new connector: one entry here, one label in source_resolver.py.
# Unknown connectors (Namespace.Function pattern not listed here) are
# detected automatically and surfaced as source_type="connector_unknown"
# with the raw function name stored in connector_fn for user labelling.
# ---------------------------------------------------------------------------

# (pattern_substring, source_type)
# Checked via `pattern in content` after comment stripping.
# Order matters — more specific checks first.
_CONNECTOR_CHECKS = [
    # Dataflows
    ("PowerBI.Dataflows(",          "dataflow_pbi"),
    ("PowerPlatform.Dataflows(",    "dataflow_platform"),
    # SQL
    ("Sql.Database(",               "sql"),
    ("AzureSQL.Database(",          "sql"),
    # Cloud storage / data platforms
    ("AzureStorage.BlobContents(",  "azure_storage"),
    ("AzureStorage.Blobs(",         "azure_storage"),
    ("AzureDataLake.Contents(",     "adls"),
    ("AzureBlobStorage.Contents(",  "azure_storage"),
    ("Lakehouse.Contents(",         "lakehouse"),
    ("Warehouse.Contents(",         "fabric_warehouse"),
    ("Databricks.Catalogs(",        "databricks"),
    ("Databricks.Contents(",        "databricks"),
    ("Snowflake.Databases(",        "snowflake"),
    # SharePoint / Files
    ("SharePoint.Files(",           "sharepoint_files"),
    ("SharePoint.Tables(",          "sharepoint_tables"),
    # Excel / CSV / local files
    ("Excel.Workbook(",             "excel_local"),
    ("Csv.Document(",               "csv_local"),
    # Web / API
    ("Web.Contents(",               "web_api"),
    ("OData.Feed(",                 "odata"),
    # ODBC / OLEDB
    ("Odbc.DataSource(",            "odbc"),
    ("OleDb.Query(",                "oledb"),
    # Smartsheet
    ("SmartsheetGlobal.Contents(",  "smartsheet"),
    ("Smartsheet.Tables(",          "smartsheet"),
    # Google
    ("GoogleAnalytics.Accounts(",   "google_analytics"),
    ("GoogleBigQuery.Database(",    "bigquery"),
    # Salesforce
    ("Salesforce.Data(",            "salesforce"),
    ("Salesforce.Reports(",         "salesforce"),
    # Other common connectors
    ("Exchange.Contents(",          "exchange"),
    ("ActiveDirectory.Domains(",    "active_directory"),
    ("SapHana.Database(",           "sap_hana"),
    ("SapBusinessWarehouse.Cubes(", "sap_bw"),
    ("Oracle.Database(",            "oracle"),
    ("MySql.Database(",             "mysql"),
    ("PostgreSQL.Database(",        "postgresql"),
    ("Teradata.Database(",          "teradata"),
    ("DB2.Database(",               "db2"),
    # Inline / hardcoded
    ("Table.FromRows(",             "embedded"),
    ("#table(",                     "hardcoded"),
]

# Transformation functions — these are NOT sources, ignore them
# when detecting `Table.Combine` specifically for appends/unions.
_TRANSFORM_FNS = {
    "Table.NestedJoin",
    "Table.MergeQueries",
    "Table.Join",
}


# ---------------------------------------------------------------------------
# Table classification
# ---------------------------------------------------------------------------

def _classify_table(name: str, partition_type: str, content: str) -> str:
    n = name.lower()
    if re.search(r"^\s*calculationGroup\s*$", content, re.MULTILINE):
        return "calc_group"
    if partition_type == "calculated":
        if re.search(r"NAMEOF\s*\(", content):
            return "field_parameter"
        return "calculated"
    if not partition_type or partition_type == "":
        if not re.search(r"\bpartition\b", content):
            return "measures_only"
    if n.startswith("fact") or n.startswith("fct"):
        return "fact"
    if n.startswith("dim") or n.startswith("d_") or n.startswith("d-"):
        return "dim"
    if n.startswith("param") or n.endswith("selector") or n.endswith("parameter"):
        return "field_parameter"
    if n.startswith("_") or n == "measures" or "measure" in n:
        return "measures_only"
    if n.startswith("source") or n.startswith("src"):
        return "staging"
    if n.startswith("helper") or n.startswith("hlp"):
        return "helper"
    if n.startswith("calc") or n.startswith("cg"):
        return "calc_group"
    return "other"


# ---------------------------------------------------------------------------
# Low-level block extractor
# ---------------------------------------------------------------------------

def _extract_blocks(text: str, keyword: str) -> list:
    results = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith(keyword):
            base_indent = len(lines[i]) - len(lines[i].lstrip("\t "))
            block = [lines[i]]
            i += 1
            while i < len(lines):
                if lines[i].strip() == "":
                    block.append(lines[i])
                    i += 1
                    continue
                current_indent = len(lines[i]) - len(lines[i].lstrip("\t "))
                if current_indent > base_indent:
                    block.append(lines[i])
                    i += 1
                else:
                    break
            results.append("\n".join(block))
        else:
            i += 1
    return results


# ---------------------------------------------------------------------------
# Column parser
# ---------------------------------------------------------------------------

def _parse_column(block: str) -> Optional[Column]:
    lines = block.strip().split("\n")
    header = lines[0].strip()

    calc = re.match(r"column\s+'(.+?)'\s*=|column\s+\"(.+?)\"\s*=", header)
    if calc:
        name = (calc.group(1) or calc.group(2)).strip()
        dax_lines = []
        for line in lines[1:]:
            s = line.strip()
            if re.match(r"(lineageTag|summarizeBy|annotation|formatString|isHidden|sortByColumn|extendedProperty|dataCategory):", s):
                break
            dax_lines.append(line)
        dax = "\n".join(dax_lines).strip().lstrip("=").strip()
        return Column(name=name, data_type="calculated", is_calculated=True,
                      dax_expression=dax, is_hidden="isHidden" in block)

    plain = re.match(r"column\s+'(.+?)'$|column\s+\"(.+?)\"$|column\s+(\S+)$", header)
    if plain:
        name = (plain.group(1) or plain.group(2) or plain.group(3)).strip()
        dt = re.search(r"dataType:\s*(\S+)", block)
        return Column(
            name=name,
            data_type=dt.group(1) if dt else "unknown",
            is_hidden="isHidden" in block,
        )
    return None


# ---------------------------------------------------------------------------
# Measure parser
# ---------------------------------------------------------------------------

def _parse_measure(block: str) -> Optional[Measure]:
    lines = block.strip().split("\n")
    header = lines[0].strip()
    m = re.match(r"measure\s+'(.+?)'\s*=|measure\s+\"(.+?)\"\s*=", header)
    if not m:
        return None
    name = (m.group(1) or m.group(2)).strip()

    inline = re.match(r"measure\s+(?:'[^']+'|\"[^\"]+\")\s*=\s*(.+)$", header)
    inline_dax = inline.group(1).strip() if inline else ""

    dax_lines, in_dax = [], True
    for line in lines[1:]:
        s = line.strip()
        if re.match(r"(formatString|displayFolder|lineageTag|annotation|description):", s):
            in_dax = False
        if in_dax:
            dax_lines.append(line)

    folder = re.search(r"displayFolder:\s*(.+)", block)
    fmt    = re.search(r"formatString:\s*(.+)", block)
    desc   = re.search(r"description:\s*(.+)", block)

    multiline_dax = "\n".join(dax_lines).strip()
    return Measure(
        name=name,
        dax_expression=multiline_dax if multiline_dax else inline_dax,
        display_folder=folder.group(1).strip().strip("'\"") if folder else "",
        format_string=fmt.group(1).strip().strip("'\"") if fmt else "",
        description=desc.group(1).strip().strip("'\"") if desc else "",
    )


# ---------------------------------------------------------------------------
# Calculation items parser
# ---------------------------------------------------------------------------

def _dedent(text: str) -> str:
    lines = text.split("\n")
    indents = [len(l) - len(l.lstrip()) for l in lines if l.strip()]
    min_indent = min(indents) if indents else 0
    return "\n".join(l[min_indent:] if len(l) >= min_indent else l for l in lines).strip()


def _parse_calculation_items(content: str) -> list:
    items = []
    blocks = _extract_blocks(content, "calculationItem ")
    for block in blocks:
        header = block.strip().split("\n")[0].strip()
        name_m = (
            re.match(r"calculationItem\s+'([^']+)'", header) or
            re.match(r'calculationItem\s+"([^"]+)"', header) or
            re.match(r"calculationItem\s+(\S+)", header)
        )
        if not name_m:
            continue
        name = name_m.group(1).strip()

        ordinal_m = re.search(r"ordinal:\s*(\d+)", block)
        ordinal = int(ordinal_m.group(1)) if ordinal_m else 0

        dax = ""
        bt_m = re.search(r"expression\s*=\s*```([\s\S]*?)```", block)
        if bt_m:
            dax = _dedent(bt_m.group(1))
        else:
            inline_m = re.search(r"expression\s*=\s*(.+)", block)
            if inline_m:
                dax = inline_m.group(1).strip()

        fmt_expr = ""
        fmt_bt = re.search(r"formatStringExpression\s*=\s*```([\s\S]*?)```", block)
        if fmt_bt:
            fmt_expr = _dedent(fmt_bt.group(1))
        else:
            fmt_inline = re.search(r'formatStringExpression\s*=\s*"([^"]+)"', block)
            if fmt_inline:
                fmt_expr = fmt_inline.group(1).strip()

        items.append(CalculationItem(
            name=name,
            ordinal=ordinal,
            dax_expression=dax,
            format_string_expression=fmt_expr,
        ))

    items.sort(key=lambda x: x.ordinal)
    return items


# ---------------------------------------------------------------------------
# M comment stripping
# ---------------------------------------------------------------------------

def _strip_m_comments(content: str) -> str:
    """Remove /* ... */ block comments. Applied before any source classification."""
    return re.sub(r"/\*[\s\S]*?\*/", "", content)


# ---------------------------------------------------------------------------
# Core inline source classifier
#
# Scans the full table file content (comments stripped) for connector
# signatures. No M block extraction — we don't care where in the code
# the connector appears, only that it's there and not inside a commented block.
#
# Priority order:
#   1. Scalar helper (PBI_ResultType signals non-table output)
#   2. Table.Combine / Table.Append — union source
#   3. Known connector signatures (_CONNECTOR_CHECKS)
#   4. Unknown connector — any Namespace.Function( pattern not in known list
#   5. Derived table reference — Source = #"name" or Source = TableName
#   6. Unresolved
# ---------------------------------------------------------------------------

def _classify_m_content(content: str, table_name: str, result_type: str = "") -> SourceExpression:
    """
    Classify the data source of an M partition by scanning the full file
    content (with comments stripped). Returns a populated SourceExpression.
    """
    expr = SourceExpression(name=table_name, raw_m=content)
    clean = _strip_m_comments(content)

    # 1. Scalar helper
    if result_type in ("Text", "Number", "Date", "DateTime", "Boolean"):
        expr.source_type = "scalar_helper"
        return expr

    # 2. Table.Combine / Table.Append — these ARE the source, not transformations
    #    Table.Combine({QueryA, QueryB, ...}) — extract referenced names
    combine = re.search(r"\bTable\.(?:Combine|Append)\s*\(\s*\{([\s\S]*?)\}\s*\)", clean)
    if combine:
        expr.source_type = "table_combine"
        # Extract #"Name" references first, then bare identifiers
        refs = re.findall(r'#"([^"]+)"', combine.group(1))
        if not refs:
            refs = re.findall(r'\b([A-Za-z_][A-Za-z0-9_]*)\b', combine.group(1))
        expr.combine_sources = [r.strip() for r in refs if r.strip()]
        return expr

    # 3. Known connector signatures — checked in priority order
    for fn_pattern, source_type in _CONNECTOR_CHECKS:
        if fn_pattern in clean:
            expr.source_type = source_type
            # Extract detail fields for connectors that have them
            _extract_connector_details(expr, clean, source_type)
            return expr

    # 4. Unknown connector — detect any Namespace.Function( pattern not already matched
    #    Ignore transformation functions (NestedJoin, MergeQueries, etc.)
    unknown = re.search(r'\b([A-Z][A-Za-z]+\.[A-Z][A-Za-z]+)\s*\(', clean)
    if unknown:
        fn = unknown.group(1)
        if fn not in _TRANSFORM_FNS and not fn.startswith("Table.") and not fn.startswith("List.") \
                and not fn.startswith("Text.") and not fn.startswith("Number.") \
                and not fn.startswith("Date.") and not fn.startswith("DateTime.") \
                and not fn.startswith("Record.") and not fn.startswith("Json.") \
                and not fn.startswith("Binary.") and not fn.startswith("Splitter.") \
                and not fn.startswith("Combiner.") and not fn.startswith("Replacer."):
            expr.source_type = "connector_unknown"
            expr.connector_fn = fn
            return expr

    # 5a. Derived — references a shared expression: Source = #"name"
    ref_quoted = re.search(r'\bSource\s*=\s*#"([^"]+)"', clean)
    if ref_quoted:
        expr.source_type = "derived"
        expr.derived_from = ref_quoted.group(1)
        return expr

    # 5b. Derived table — bare table name as first Source step
    #     Matches: Source = SomeName, (with comma or newline after)
    #     Excludes known M stdlib prefixes and anything followed by (
    ref_bare = re.search(
        r'\bSource\s*=\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?=,|\n|$)',
        clean, re.MULTILINE
    )
    if ref_bare:
        ref = ref_bare.group(1).strip()
        after = clean[ref_bare.end():].lstrip()
        if not after.startswith("(") and ref not in (
            "let", "in", "each", "true", "false", "null",
            "Table", "List", "Record", "Json", "Xml", "Csv",
            "Excel", "File", "Text", "Date", "DateTime", "Binary",
            "Number", "Duration", "Time", "Splitter", "Combiner",
        ):
            expr.source_type = "derived_table"
            expr.derived_from = ref
            return expr

    # 6. Unresolved
    return expr


def _extract_connector_details(expr: SourceExpression, clean: str, source_type: str) -> None:
    """Populates detail fields on expr based on source_type. Mutates in place."""

    if source_type in ("dataflow_pbi", "dataflow_platform"):
        wid    = re.search(r'workspaceId\s*=\s*"([^"]+)"', clean)
        dfid   = re.search(r'dataflowId\s*=\s*"([^"]+)"', clean)
        entity = re.search(r'entity\s*=\s*"([^"]+)"', clean)
        if wid:    expr.workspace_id = wid.group(1)
        if dfid:   expr.dataflow_id  = dfid.group(1)
        if entity: expr.entity       = entity.group(1)

    elif source_type in ("sql", "sql_native_query"):
        sql_m = re.search(r'(?:Sql|AzureSQL)\.Database\s*\(\s*"([^"]+)"\s*,\s*"([^"]+)"', clean)
        if sql_m:
            expr.server   = sql_m.group(1)
            expr.database = sql_m.group(2)
        native = re.search(r'\[Query\s*=\s*"([^"]+)"\]', clean)
        if native:
            expr.source_type  = "sql_native_query"
            expr.native_query = native.group(1)
        else:
            tbl = re.search(r'Schema\s*=\s*"([^"]+)"\s*,\s*Item\s*=\s*"([^"]+)"', clean)
            if tbl:
                expr.schema        = tbl.group(1)
                expr.table_or_view = tbl.group(2)

    elif source_type == "odbc":
        dsn = re.search(r'Odbc\.DataSource\s*\(\s*"([^"]+)"', clean)
        if dsn:
            expr.dsn = dsn.group(1)

    elif source_type in ("sharepoint_files", "sharepoint_tables", "excel_sharepoint"):
        sp = re.search(r'SharePoint\.(?:Files|Tables)\s*\(\s*"([^"]+)"', clean)
        if sp:
            expr.sharepoint_url = sp.group(1)
        fn = re.search(r'\[Name\]\s*=\s*"([^"]+\.xlsx?)"', clean)
        if fn:
            expr.file_name   = fn.group(1)
            expr.source_type = "excel_sharepoint"
        lst = re.search(r'Name\s*=\s*"([^"]+)"', clean)
        if lst and not fn:
            expr.table_or_view = lst.group(1)

    elif source_type == "excel_local":
        fn = re.search(r'File\.Contents\s*\(\s*"([^"]+)"', clean)
        if fn:
            expr.file_name = fn.group(1)
        sheet = re.search(r'Item\s*=\s*"([^"]+)"', clean)
        if sheet:
            expr.sheet_name = sheet.group(1)
        if "SharePoint.Files" in clean:
            expr.source_type = "excel_sharepoint"
            sp = re.search(r'SharePoint\.Files\s*\(\s*"([^"]+)"', clean)
            if sp:
                expr.sharepoint_url = sp.group(1)

    elif source_type == "csv_local":
        fn = re.search(r'File\.Contents\s*\(\s*"([^"]+)"', clean)
        if fn:
            expr.file_name = fn.group(1)

    elif source_type in ("web_api", "odata"):
        url = re.search(r'(?:Web\.Contents|OData\.Feed)\s*\(\s*"([^"]+)"', clean)
        if url:
            expr.url = url.group(1)
        entity = re.search(r'Name\s*=\s*"([^"]+)"', clean)
        if entity:
            expr.table_or_view = entity.group(1)

    elif source_type == "smartsheet":
        region = re.search(r'SmartsheetGlobal\.Contents\s*\(\s*"([^"]+)"', clean)
        if region:
            expr.url = region.group(1)


# ---------------------------------------------------------------------------
# Table partition source_ref extractor
#
# Only returns a value when the partition source is a bare #"expression-name"
# reference pointing to expressions.tmdl — no let block, no inline M.
# ---------------------------------------------------------------------------

def _extract_partition_source_ref(content: str) -> str:
    """
    Returns the expression name if this table's partition is a simple
    #"expression-name" pointer to expressions.tmdl. Returns "" otherwise.
    """
    # Backtick-delimited block
    bt = re.search(r"source\s*=\s*```([\s\S]*?)```", content)
    if bt:
        block = bt.group(1).strip()
        if "let" not in block.lower():
            ref = re.match(r'^#"([^"]+)"\s*$', block)
            if ref:
                return ref.group(1)
        return ""

    # Plain inline block — look for source = #"name" with no let block after it
    # Use a simple regex on the full content
    m = re.search(r'^\s*source\s*=\s*#"([^"]+)"\s*$', content, re.MULTILINE)
    if m:
        return m.group(1)

    return ""


# ---------------------------------------------------------------------------
# Table file parser
# ---------------------------------------------------------------------------

def _parse_table_file(filepath: str) -> Optional[Table]:
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    for raw_line in content.split("\n"):
        line = raw_line.strip()
        if not line or line.startswith("//"):
            continue
        name_match = re.match(r"^table\s+(.+)$", line)
        if not name_match:
            return None
        name = name_match.group(1).strip().strip("'\"")
        break
    else:
        return None

    qg = re.search(r"queryGroup:\s*'?([^'\n]+)'?", content)
    query_group = qg.group(1).strip().strip("'\"") if qg else ""

    # Partition type — handles quoted names with spaces: partition 'My Table' = m
    pt = re.search(
        r"^\s*partition\s+(?:'[^']*'|\"[^\"]*\"|\S+)\s*=\s*(\w+)",
        content, re.MULTILINE
    )
    partition_type = pt.group(1).strip() if pt else ""

    # PBI_ResultType annotation — for scalar helper detection
    rt_m = re.search(r"PBI_ResultType\s*=\s*(\S+)", content)
    result_type = rt_m.group(1).strip() if rt_m else ""

    table_type = _classify_table(name, partition_type, content)
    is_hidden  = bool(re.search(r"changedProperty\s*=\s*IsHidden", content))
    is_loaded  = "TabularEditor_EnableLoad = false" not in content
    source_ref = _extract_partition_source_ref(content) if partition_type == "m" else ""

    dax_partition = ""
    if partition_type == "calculated":
        dax_m = re.search(
            r"^\s*source\s*=\s*([\s\S]+?)(?=\n\s*annotation|\n\s*changedProperty|\Z)",
            content, re.MULTILINE
        )
        if dax_m:
            dax_partition = dax_m.group(1).strip()

    # Classify inline M by scanning the full file content
    inline_source = None
    if partition_type == "m" and not source_ref:
        inline_source = _classify_m_content(content, name, result_type)

    columns           = [c for b in _extract_blocks(content, "column ")  for c in [_parse_column(b)]  if c]
    measures          = [m for b in _extract_blocks(content, "measure ")  for m in [_parse_measure(b)] if m]
    calculation_items = _parse_calculation_items(content) if table_type == "calc_group" else []

    return Table(
        name=name,
        table_type=table_type,
        query_group=query_group,
        partition_type=partition_type,
        source_ref=source_ref,
        is_hidden=is_hidden,
        is_loaded=is_loaded,
        columns=columns,
        measures=measures,
        calculation_items=calculation_items,
        dax_partition=dax_partition,
        inline_source=inline_source,
    )


# ---------------------------------------------------------------------------
# Relationship parser
# ---------------------------------------------------------------------------

def _parse_relationships(filepath: str) -> list:
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    rels = []
    normalised = re.sub(r"^relationship\s+", "\nrelationship ", content, count=1)
    for block in re.split(r"\nrelationship\s+", normalised):
        from_m = re.search(r"fromColumn:\s*(.+?)\.(.+)", block)
        to_m   = re.search(r"toColumn:\s*(.+?)\.(.+)", block)
        card_m = re.search(r"fromCardinality:\s*(\S+)", block)
        active = "isActive: false" not in block
        if from_m and to_m:
            rels.append(Relationship(
                from_table=from_m.group(1).strip().strip("'\""),
                from_column=from_m.group(2).strip().strip("'\""),
                to_table=to_m.group(1).strip().strip("'\""),
                to_column=to_m.group(2).strip().strip("'\""),
                cardinality=card_m.group(1).strip() if card_m else "",
                is_active=active,
            ))
    return rels


# ---------------------------------------------------------------------------
# Roles parser
# ---------------------------------------------------------------------------

def _parse_roles(filepath: str) -> list:
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    roles = []
    normalised = re.sub(r"^role\s+", "\nrole ", content, count=1)
    for block in re.split(r"\nrole\s+", normalised):
        block = block.strip()
        if not block:
            continue

        name_m = (
            re.match(r"'([^']+)'", block) or
            re.match(r'"([^"]+)"', block) or
            re.match(r"(\S+)", block)
        )
        if not name_m:
            continue
        name = name_m.group(1).strip()
        if name.startswith("//"):
            continue

        filters = []
        for perm in re.finditer(
            r"tablePermission\s+(?:'([^']+)'|\"([^\"]+)\"|(\S+))\s*=\s*(.+)",
            block
        ):
            table_name = (perm.group(1) or perm.group(2) or perm.group(3)).strip()
            dax_filter = perm.group(4).strip()
            filters.append(TableFilter(table=table_name, dax_filter=dax_filter))

        is_dynamic = False
        dynamic_fn = ""
        all_dax = " ".join(f.dax_filter for f in filters)
        if "USERPRINCIPALNAME()" in all_dax.upper():
            is_dynamic, dynamic_fn = True, "USERPRINCIPALNAME"
        elif "USERNAME()" in all_dax.upper():
            is_dynamic, dynamic_fn = True, "USERNAME"

        roles.append(SecurityRole(
            name=name,
            table_filters=filters,
            is_dynamic=is_dynamic,
            dynamic_function=dynamic_fn,
        ))

    return roles


# ---------------------------------------------------------------------------
# Expression classifier (expressions.tmdl)
#
# Shared expressions already have their M extracted cleanly by the
# expressions parser, so we use the same content-scan approach here.
# ---------------------------------------------------------------------------

def _classify_expression(block: str, name: str) -> SourceExpression:
    expr = SourceExpression(name=name, raw_m=block)

    qg = re.search(r"queryGroup:\s*'?([^'\n]+)'?", block)
    if qg:
        expr.query_group = qg.group(1).strip().strip("'\"")

    # M Parameter
    if "IsParameterQuery=true" in block or "IsParameterQuery = true" in block:
        expr.source_type = "parameter"
        val = re.match(r"['\"]?" + re.escape(name) + r"['\"]?\s*=\s*(.+?)\s+meta", block, re.DOTALL)
        if val:
            expr.param_value = val.group(1).strip().strip('"')
        t = re.search(r'Type\s*=\s*"([^"]+)"', block)
        expr.param_type = t.group(1) if t else "Text"
        return expr

    # Function definition
    if re.search(r"^\s*\([^)]*\)\s*=>", block, re.MULTILINE):
        expr.source_type = "function_def"
        return expr

    # Scalar helper
    rt_m = re.search(r"PBI_ResultType\s*=\s*(\S+)", block)
    rt = rt_m.group(1).strip() if rt_m else ""
    if rt in ("Date", "DateTime", "Number", "Text", "Boolean") and "Table" not in rt:
        expr.source_type = "scalar_helper"
        return expr

    # Use the same content-scan classifier
    classified = _classify_m_content(block, name)
    classified.query_group = expr.query_group
    return classified


# ---------------------------------------------------------------------------
# Expressions.tmdl parser
# ---------------------------------------------------------------------------

def _parse_expressions(filepath: str) -> tuple[list, list]:
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    source_expressions: list[SourceExpression] = []
    m_parameters: list[MParameter] = []

    blocks = re.split(r"(?:^|\n)expression\s+", content)
    for block in blocks:
        block = block.strip()
        if not block:
            continue

        name_m = (
            re.match(r"'([^']+)'\s*=", block) or
            re.match(r'"([^"]+)"\s*=', block) or
            re.match(r"([^\s=]+)\s*=", block)
        )
        if not name_m:
            continue
        name = name_m.group(1).strip()
        if name.startswith("//"):
            continue

        expr = _classify_expression(block, name)

        if expr.source_type == "parameter":
            m_parameters.append(MParameter(
                name=name,
                value=expr.param_value,
                param_type=expr.param_type,
            ))
        else:
            source_expressions.append(expr)

    return source_expressions, m_parameters


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def parse_semantic_model(model_folder: str, report_name: str) -> SemanticModel:
    model = SemanticModel(report_name=report_name)
    definition_path = os.path.join(model_folder, "definition")

    if not os.path.isdir(definition_path):
        return model

    expressions_file = os.path.join(definition_path, "expressions.tmdl")
    if os.path.exists(expressions_file):
        model.source_expressions, model.m_parameters = _parse_expressions(expressions_file)

    relationships_file = os.path.join(definition_path, "relationships.tmdl")
    if os.path.exists(relationships_file):
        model.relationships = _parse_relationships(relationships_file)

    roles_file = os.path.join(definition_path, "roles.tmdl")
    if os.path.exists(roles_file):
        model.security_roles = _parse_roles(roles_file)

    tables_path = os.path.join(definition_path, "tables")
    if os.path.isdir(tables_path):
        for filename in sorted(os.listdir(tables_path)):
            if filename.endswith(".tmdl"):
                tbl = _parse_table_file(os.path.join(tables_path, filename))
                if tbl:
                    model.tables.append(tbl)

    return model
