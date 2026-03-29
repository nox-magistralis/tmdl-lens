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
    table_filters: list = field(default_factory=list)  # list[TableFilter]
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

    source_type is the primary classification used by the resolver:
      dataflow_pbi       PowerBI.Dataflows()
      dataflow_platform  PowerPlatform.Dataflows()
      sql                Sql.Database()
      sql_native_query   Sql.Database() with [Query=...]
      odbc               Odbc.DataSource()
      sharepoint_files   SharePoint.Files()
      sharepoint_tables  SharePoint.Tables()
      excel_sharepoint   Excel.Workbook() fetched via SharePoint.Files()
      excel_local        Excel.Workbook(File.Contents(...))
      csv_local          Csv.Document(File.Contents(...))
      web_api            Web.Contents()
      odata              OData.Feed()
      hardcoded          #table(...) inline data
      derived            references another query via Source = #"name"
      custom_function    calls a user-defined M function
      parameter          IsParameterQuery = true
      function_def       function definition (not a data table)
      scalar_helper      returns a scalar value, not a table
      unknown            could not be classified
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

    # Derived / custom-function fields
    derived_from: str = ""
    function_name: str = ""
    function_args: str = ""

    # Parameter fields
    param_value: str = ""
    param_type: str = ""


@dataclass
class Table:
    name: str
    table_type: str          # see _classify_table()
    query_group: str = ""
    partition_type: str = "" # "m", "calculated", ""
    source_ref: str = ""     # name of the SourceExpression this table points to
    is_hidden: bool = False
    is_loaded: bool = True
    columns: list = field(default_factory=list)
    measures: list = field(default_factory=list)
    calculation_items: list = field(default_factory=list)  # list[CalculationItem]
    dax_partition: str = ""  # raw DAX for calculated tables / field parameters


@dataclass
class SemanticModel:
    report_name: str
    tables: list = field(default_factory=list)
    relationships: list = field(default_factory=list)
    source_expressions: list = field(default_factory=list)
    m_parameters: list = field(default_factory=list)
    security_roles: list = field(default_factory=list)  # list[SecurityRole]


# ---------------------------------------------------------------------------
# Table classification
# ---------------------------------------------------------------------------

def _classify_table(name: str, partition_type: str, content: str) -> str:
    n = name.lower()
    # Structural checks first — definitive regardless of name
    if re.search(r"^\s*calculationGroup\s*$", content, re.MULTILINE):
        return "calc_group"
    if partition_type == "calculated":
        if re.search(r"NAMEOF\s*\(", content):
            return "field_parameter"
        return "calculated"
    if not partition_type or partition_type == "":
        if not re.search(r"\bpartition\b", content):
            return "measures_only"
    # Name-based heuristics for everything else
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
    """
    Extracts indented blocks that start with `keyword` at any indent level.
    Returns each block as a string including its header line.
    """
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
        dax_lines, in_dax = [], False
        for line in lines[1:]:
            s = line.strip()
            if re.match(r"(lineageTag|summarizeBy|annotation|formatString|isHidden|sortByColumn|extendedProperty|dataCategory):", s):
                break
            in_dax = True
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
            is_hidden="isHidden" in block
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

    # Capture inline DAX on the header line: measure 'Name' = DAX_EXPRESSION
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
    final_dax = multiline_dax if multiline_dax else inline_dax

    return Measure(
        name=name,
        dax_expression=final_dax,
        display_folder=folder.group(1).strip().strip("'\"") if folder else "",
        format_string=fmt.group(1).strip().strip("'\"") if fmt else "",
        description=desc.group(1).strip().strip("'\"") if desc else "",
    )


# ---------------------------------------------------------------------------
# Calculation items parser
# ---------------------------------------------------------------------------

def _parse_calculation_items(content: str) -> list:
    """
    Extracts calculationItem blocks from a calc group table file.
    Handles backtick-delimited DAX expressions and optional ordinal/formatStringExpression.
    """
    items = []
    blocks = _extract_blocks(content, "calculationItem ")
    for block in blocks:
        header = block.strip().split("\n")[0].strip()
        # Name may be quoted or unquoted: calculationItem 'YTD' or calculationItem YTD
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

        # DAX expression — backtick block or inline after =
        dax = ""
        bt_m = re.search(r"expression\s*=\s*```([\s\S]*?)```", block)
        if bt_m:
            dax = bt_m.group(1).strip()
        else:
            inline_m = re.search(r"expression\s*=\s*(.+)", block)
            if inline_m:
                dax = inline_m.group(1).strip()

        # Format string expression — backtick block or quoted string
        fmt_expr = ""
        fmt_bt = re.search(r"formatStringExpression\s*=\s*```([\s\S]*?)```", block)
        if fmt_bt:
            fmt_expr = fmt_bt.group(1).strip()
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

    # Sort by ordinal so output order is stable regardless of file order
    items.sort(key=lambda x: x.ordinal)
    return items


# ---------------------------------------------------------------------------
# Table partition M source extractor
# ---------------------------------------------------------------------------

def _extract_partition_source_ref(content: str) -> str:
    """
    Returns the shared expression name when a table partition starts with:
        Source = #"expression-name"
    Returns "" if not a simple expression reference.
    """
    bt = re.search(r"source\s*=\s*```([\s\S]*?)```", content)
    m_block = bt.group(1) if bt else content

    ref = re.search(r'^\s*Source\s*=\s*#"([^"]+)"', m_block, re.MULTILINE)
    if ref:
        return ref.group(1)

    direct = re.search(r'^\s*source\s*=\s*#"([^"]+)"', content, re.MULTILINE)
    if direct:
        return direct.group(1)

    return ""


# ---------------------------------------------------------------------------
# Table file parser
# ---------------------------------------------------------------------------

def _parse_table_file(filepath: str) -> Optional[Table]:
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # First non-comment, non-blank line must be "table <name>"
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

    # Partition type: "m", "calculated", or absent (calc group / measures-only)
    pt = re.search(r"^\s*partition\s+\S+\s*=\s*(\w+)", content, re.MULTILINE)
    partition_type = pt.group(1).strip() if pt else ""

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
    )


# ---------------------------------------------------------------------------
# Relationship parser
# ---------------------------------------------------------------------------

def _parse_relationships(filepath: str) -> list:
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    rels = []
    # Normalise so the first block is also captured (file may not start with \n)
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
    """
    Parses a roles.tmdl file and returns a list of SecurityRole objects.
    Handles static RLS, dynamic RLS (USERPRINCIPALNAME / USERNAME), multi-table
    filters, and full-access roles with no filters.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    roles = []
    # Normalise first block same way as relationships
    normalised = re.sub(r"^role\s+", "\nrole ", content, count=1)
    for block in re.split(r"\nrole\s+", normalised):
        block = block.strip()
        if not block:
            continue

        # Role name — quoted or unquoted
        name_m = (
            re.match(r"'([^']+)'", block) or
            re.match(r'"([^"]+)"', block) or
            re.match(r"(\S+)", block)
        )
        if not name_m:
            continue
        name = name_m.group(1).strip()

        # Skip comment blocks pulled in by the split
        if name.startswith("//"):
            continue

        # Each tablePermission line: tablePermission 'TableName' = <dax>
        filters = []
        for perm in re.finditer(
            r"tablePermission\s+(?:'([^']+)'|\"([^\"]+)\"|(\S+))\s*=\s*(.+)",
            block
        ):
            table_name = (perm.group(1) or perm.group(2) or perm.group(3)).strip()
            dax_filter = perm.group(4).strip()
            filters.append(TableFilter(table=table_name, dax_filter=dax_filter))

        # Detect dynamic RLS from any filter expression
        is_dynamic = False
        dynamic_fn = ""
        all_dax = " ".join(f.dax_filter for f in filters)
        if "USERPRINCIPALNAME()" in all_dax.upper():
            is_dynamic = True
            dynamic_fn = "USERPRINCIPALNAME"
        elif "USERNAME()" in all_dax.upper():
            is_dynamic = True
            dynamic_fn = "USERNAME"

        roles.append(SecurityRole(
            name=name,
            table_filters=filters,
            is_dynamic=is_dynamic,
            dynamic_function=dynamic_fn,
        ))

    return roles


# ---------------------------------------------------------------------------
# Expression classifier
# ---------------------------------------------------------------------------

def _classify_expression(block: str, name: str) -> SourceExpression:
    """
    Classifies a single expression block and populates a SourceExpression.
    Tier 1: direct source connectors.
    Tier 2: derived / parameter reference / custom function call.
    Tier 3: dynamic M (unresolvable).
    Special: M parameters, function definitions, scalar helpers.
    """
    expr = SourceExpression(name=name, raw_m=block)

    qg = re.search(r"queryGroup:\s*'?([^'\n]+)'?", block)
    if qg:
        expr.query_group = qg.group(1).strip().strip("'\"")

    result_type = re.search(r"PBI_ResultType\s*=\s*(\S+)", block)
    rt = result_type.group(1).strip() if result_type else ""

    # ── M Parameter ──────────────────────────────────────────────────────────
    if "IsParameterQuery=true" in block or "IsParameterQuery = true" in block:
        expr.source_type = "parameter"
        val = re.match(r"['\"]?" + re.escape(name) + r"['\"]?\s*=\s*(.+?)\s+meta", block, re.DOTALL)
        if val:
            expr.param_value = val.group(1).strip().strip('"')
        t = re.search(r'Type\s*=\s*"([^"]+)"', block)
        expr.param_type = t.group(1) if t else "Text"
        return expr

    # ── Function definition ───────────────────────────────────────────────────
    if re.search(r"^\s*\([^)]*\)\s*=>", block, re.MULTILINE):
        expr.source_type = "function_def"
        return expr

    # ── Scalar helper (returns Date, Number, etc., not a Table) ───────────────
    if rt in ("Date", "DateTime", "Number", "Text", "Boolean") and "Table" not in rt:
        expr.source_type = "scalar_helper"
        return expr

    # ── Tier 1: PowerBI.Dataflows() ──────────────────────────────────────────
    if re.search(r"\bPowerBI\.Dataflows\s*\(", block):
        expr.source_type = "dataflow_pbi"
        wid    = re.search(r'workspaceId\s*=\s*"([^"]+)"', block)
        dfid   = re.search(r'dataflowId\s*=\s*"([^"]+)"', block)
        entity = re.search(r'entity\s*=\s*"([^"]+)"', block)
        if wid:    expr.workspace_id = wid.group(1)
        if dfid:   expr.dataflow_id  = dfid.group(1)
        if entity: expr.entity       = entity.group(1)
        return expr

    # ── Tier 1: PowerPlatform.Dataflows() ────────────────────────────────────
    if re.search(r"\bPowerPlatform\.Dataflows\s*\(", block):
        expr.source_type = "dataflow_platform"
        wid    = re.search(r'workspaceId\s*=\s*"([^"]+)"', block)
        dfid   = re.search(r'dataflowId\s*=\s*"([^"]+)"', block)
        entity = re.search(r'entity\s*=\s*"([^"]+)"', block)
        if wid:    expr.workspace_id = wid.group(1)
        if dfid:   expr.dataflow_id  = dfid.group(1)
        if entity: expr.entity       = entity.group(1)
        return expr

    # ── Tier 1: Sql.Database() ───────────────────────────────────────────────
    sql_m = re.search(
        r'Sql\.Database\s*\(\s*"([^"]+)"\s*,\s*"([^"]+)"'
        r'(?:\s*,\s*\[Query\s*=\s*"([^"]+)"\])?',
        block, re.DOTALL
    )
    if sql_m:
        expr.server   = sql_m.group(1)
        expr.database = sql_m.group(2)
        if sql_m.group(3):
            expr.source_type  = "sql_native_query"
            expr.native_query = sql_m.group(3)
        else:
            expr.source_type = "sql"
            tbl = re.search(r'Schema\s*=\s*"([^"]+)"\s*,\s*Item\s*=\s*"([^"]+)"', block)
            if tbl:
                expr.schema        = tbl.group(1)
                expr.table_or_view = tbl.group(2)
        return expr

    # ── Tier 2: Sql.Database() with parameter references ─────────────────────
    sql_param = re.search(r'Sql\.Database\s*\(\s*([A-Za-z_]\w*)\s*,\s*([A-Za-z_]\w*)', block)
    if sql_param:
        expr.source_type = "sql"
        expr.server   = f"[param:{sql_param.group(1)}]"
        expr.database = f"[param:{sql_param.group(2)}]"
        tbl = re.search(r'Schema\s*=\s*"([^"]+)"\s*,\s*Item\s*=\s*"([^"]+)"', block)
        if tbl:
            expr.schema        = tbl.group(1)
            expr.table_or_view = tbl.group(2)
        return expr

    # ── Tier 1: Odbc.DataSource() ────────────────────────────────────────────
    odbc_m = re.search(r'Odbc\.DataSource\s*\(\s*"([^"]+)"', block)
    if odbc_m:
        expr.source_type = "odbc"
        expr.dsn = odbc_m.group(1)
        tbl = re.search(r'Name\s*=\s*"([^"]+)"\s*\]\[Data\].*?Name\s*=\s*"([^"]+)"', block, re.DOTALL)
        if tbl:
            expr.schema        = tbl.group(1)
            expr.table_or_view = tbl.group(2)
        return expr

    # ── Tier 1: SharePoint.Tables() ──────────────────────────────────────────
    spt_m = re.search(r'SharePoint\.Tables\s*\(\s*"([^"]+)"', block)
    if spt_m:
        expr.source_type    = "sharepoint_tables"
        expr.sharepoint_url = spt_m.group(1)
        list_name = re.search(r'Name\s*=\s*"([^"]+)"', block)
        if list_name:
            expr.table_or_view = list_name.group(1)
        return expr

    # ── Tier 1: Excel.Workbook() from SharePoint.Files() ─────────────────────
    if "Excel.Workbook" in block and "SharePoint.Files" in block:
        expr.source_type = "excel_sharepoint"
        sp = re.search(r'SharePoint\.Files\s*\(\s*"([^"]+)"', block)
        if sp:
            expr.sharepoint_url = sp.group(1)
        fn = re.search(r'\[Name\]\s*=\s*"([^"]+\.xlsx?)"', block)
        if fn:
            expr.file_name = fn.group(1)
        sheet = re.search(r'Item\s*=\s*"([^"]+)"', block)
        if sheet:
            expr.sheet_name = sheet.group(1)
        return expr

    # ── Tier 1: SharePoint.Files() → CSV ─────────────────────────────────────
    if "SharePoint.Files" in block:
        expr.source_type = "sharepoint_files"
        sp = re.search(r'SharePoint\.Files\s*\(\s*"([^"]+)"', block)
        if sp:
            expr.sharepoint_url = sp.group(1)
        fn = re.search(r'Name\]\s*=\s*"([^"]+)"', block)
        if fn:
            expr.file_name = fn.group(1)
        return expr

    # ── Tier 1: Excel.Workbook() from local file ─────────────────────────────
    excel_local = re.search(r'Excel\.Workbook\s*\(File\.Contents\s*\(\s*"([^"]+)"', block)
    if excel_local:
        expr.source_type = "excel_local"
        expr.file_name   = excel_local.group(1)
        sheet = re.search(r'Item\s*=\s*"([^"]+)"', block)
        if sheet:
            expr.sheet_name = sheet.group(1)
        return expr

    # ── Tier 1: Csv.Document() from local file ────────────────────────────────
    csv_local = re.search(r'Csv\.Document\s*\(\s*File\.Contents\s*\(\s*"([^"]+)"', block, re.DOTALL)
    if csv_local:
        expr.source_type = "csv_local"
        expr.file_name   = csv_local.group(1)
        return expr

    # ── Tier 1: OData.Feed() ─────────────────────────────────────────────────
    odata_m = re.search(r'OData\.Feed\s*\(\s*"([^"]+)"', block)
    if odata_m:
        expr.source_type = "odata"
        expr.url         = odata_m.group(1)
        entity_name = re.search(r'Name\s*=\s*"([^"]+)"', block)
        if entity_name:
            expr.table_or_view = entity_name.group(1)
        return expr

    # ── Tier 1: Web.Contents() with literal URL ──────────────────────────────
    web_m = re.search(r'Web\.Contents\s*\(\s*"([^"]+)"', block)
    if web_m:
        expr.source_type = "web_api"
        expr.url         = web_m.group(1)
        return expr

    # ── Tier 2: Custom function call ──────────────────────────────────────────
    fn_call = re.search(r'Source\s*=\s*([A-Za-z_]\w*)\s*\(([^)]*)\)', block)
    if fn_call and fn_call.group(1) not in (
        "Table", "List", "Record", "Json", "Xml",
        "Csv", "Excel", "File", "Text", "Date", "DateTime"
    ):
        expr.source_type   = "custom_function"
        expr.function_name = fn_call.group(1)
        expr.function_args = fn_call.group(2).strip()
        return expr

    # ── Tier 2: Derived — references another expression ──────────────────────
    derived = re.search(r'\bSource\s*=\s*#"([^"]+)"', block)
    if derived:
        expr.source_type  = "derived"
        expr.derived_from = derived.group(1)
        return expr

    # ── Tier 3: Dynamic / unresolvable ───────────────────────────────────────
    if re.search(r"\s&\s", block):
        expr.source_type = "dynamic"
        return expr

    # ── Tier 1: #table() hardcoded ───────────────────────────────────────────
    if re.search(r"#table\s*\(", block):
        expr.source_type = "hardcoded"
        return expr

    return expr


# ---------------------------------------------------------------------------
# Expressions.tmdl parser
# ---------------------------------------------------------------------------

def _parse_expressions(filepath: str) -> tuple[list, list]:
    """Returns (source_expressions, m_parameters). Splits on 'expression ' at line start."""
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
    """
    Parse a .SemanticModel folder and return a populated SemanticModel.

    Args:
        model_folder: path to the .SemanticModel folder
        report_name:  display name to use in the README

    Returns:
        SemanticModel dataclass
    """
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
