"""
source_resolver.py — Source resolution for tmdl-lens.

Takes the raw SourceExpression list from tmdl_parser and resolves:
  Tier 1  Direct source connectors — already fully classified by the parser.
  Tier 2  Derived expressions, parameter references, custom function calls.
          These are followed one level and resolved to their root source.
  Tier 3  Dynamic M (string concatenation, runtime variables).
          Flagged as unresolvable; caller may offer manual override.

Also resolves inline_source on Table objects, building full -> chains.

Produces a flat dict  { table_name_or_expression_name: ResolvedSource }
used by the README generator.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from src.tmdl_parser import SourceExpression, MParameter


# ---------------------------------------------------------------------------
# ResolvedSource — the final output of resolution
# ---------------------------------------------------------------------------

@dataclass
class ResolvedSource:
    expression_name: str
    source_type: str
    resolution_tier: int = 1
    label: str = ""

    # Dataflow
    workspace_id: str = ""
    dataflow_id: str = ""
    entity: str = ""

    # SQL
    server: str = ""
    database: str = ""
    schema: str = ""
    table_or_view: str = ""
    native_query: str = ""

    # ODBC
    dsn: str = ""

    # File / SharePoint
    sharepoint_url: str = ""
    file_name: str = ""
    sheet_name: str = ""

    # Web / OData
    url: str = ""
    physical_tables: list = field(default_factory=list)

    # Derivation chain
    derived_from: str = ""
    chain: list = field(default_factory=list)

    # Unresolved
    unresolved: bool = False
    unresolved_reason: str = ""

    # Manual override label
    manual_label: str = ""


# ---------------------------------------------------------------------------
# Terminal source types — chain walking stops here
# ---------------------------------------------------------------------------

_TERMINAL_TYPES = {
    # Known connectors
    "dataflow_pbi", "dataflow_platform",
    "sql", "sql_native_query",
    "odbc", "oledb",
    "sharepoint_files", "sharepoint_tables",
    "excel_sharepoint", "excel_local",
    "csv_local",
    "web_api", "odata",
    "hardcoded", "embedded",
    "smartsheet", "calc_series",
    # Cloud / platform connectors
    "azure_storage", "adls", "lakehouse", "fabric_warehouse",
    "databricks", "snowflake",
    "google_analytics", "bigquery",
    "salesforce",
    "exchange", "active_directory",
    "sap_hana", "sap_bw",
    "oracle", "mysql", "postgresql", "teradata", "db2",
    # Special
    "powerbi_dataset", "dataverse",
    "azure_devops", "dynamics_fo",
    "google_sheets", "quickbooks", "github",
    "connector_unknown",
    "dynamic", "unresolved",
    "function_def", "scalar_helper",
}

# Human-readable labels for connector source types
_CONNECTOR_LABELS = {
    "dataflow_pbi":      "Power BI Dataflow",
    "dataflow_platform": "Power Platform Dataflow",
    "sql":               "SQL Database",
    "sql_native_query":  "SQL (Native Query)",
    "odbc":              "ODBC",
    "oledb":             "OLE DB",
    "sharepoint_files":  "SharePoint Files",
    "sharepoint_tables": "SharePoint List",
    "excel_sharepoint":  "Excel (SharePoint)",
    "excel_local":       "Excel (Local)",
    "csv_local":         "CSV (Local)",
    "web_api":           "Web API",
    "odata":             "OData",
    "hardcoded":         "Hardcoded (Inline M)",
    "embedded":          "Embedded Data",
    "smartsheet":        "Smartsheet",
    "calc_series":       "Calculated Series",
    "azure_storage":     "Azure Blob Storage",
    "adls":              "Azure Data Lake Storage",
    "lakehouse":         "Microsoft Fabric Lakehouse",
    "fabric_warehouse":  "Microsoft Fabric Warehouse",
    "databricks":        "Databricks",
    "snowflake":         "Snowflake",
    "google_analytics":  "Google Analytics",
    "bigquery":          "Google BigQuery",
    "salesforce":        "Salesforce",
    "exchange":          "Exchange",
    "active_directory":  "Active Directory",
    "sap_hana":          "SAP HANA",
    "sap_bw":            "SAP BW",
    "oracle":            "Oracle Database",
    "mysql":             "MySQL",
    "postgresql":        "PostgreSQL",
    "teradata":          "Teradata",
    "db2":               "IBM Db2",
    "azure_devops":      "Azure DevOps",
    "dynamics_fo":       "Dynamics 365 Finance & Operations",
    "google_sheets":     "Google Sheets",
    "quickbooks":        "QuickBooks",
    "github":            "GitHub",
    "table_combine":     "Combined Queries",
    "dynamic":           "Dynamic M",
    "unresolved":        "Unresolved",
    "function_def":      "Helper Function",
    "scalar_helper":     "Scalar Helper",
    "powerbi_dataset":    "Power BI Dataset",
    "dataverse":          "Dataverse",
    "connector_unknown": "Unknown Connector",
}


# ---------------------------------------------------------------------------
# Label builders
# ---------------------------------------------------------------------------

def _build_label(expr: SourceExpression, params: dict[str, str]) -> str:
    t = expr.source_type

    if t in ("dataflow_pbi", "dataflow_platform"):
        connector = "Power BI Dataflow" if t == "dataflow_pbi" else "Power Platform Dataflow"
        entity = expr.entity or "?"
        return f"{connector} -> {entity}"

    if t == "sql":
        server = _resolve_param(expr.server, params)
        db     = _resolve_param(expr.database, params)
        if expr.schema and expr.table_or_view:
            return f"SQL -> {server} -> {db} -> {expr.schema}.{expr.table_or_view}"
        return f"SQL -> {server} -> {db}"

    if t == "sql_native_query":
        server = _resolve_param(expr.server, params)
        db     = _resolve_param(expr.database, params)
        return f"SQL (native query) -> {server} -> {db}"

    if t == "odbc":
        dsn = expr.dsn or "?"
        tbl = f" -> {expr.schema}.{expr.table_or_view}" if expr.table_or_view else ""
        return f"ODBC -> {dsn}{tbl}"

    if t == "sharepoint_files":
        fn = f" -> {expr.file_name}" if expr.file_name else ""
        return f"SharePoint Files -> {expr.sharepoint_url}{fn}"

    if t == "sharepoint_tables":
        lst = f" -> {expr.table_or_view}" if expr.table_or_view else ""
        return f"SharePoint List -> {expr.sharepoint_url}{lst}"

    if t == "excel_sharepoint":
        if expr.file_name:
            sheet = f" -> {expr.sheet_name}" if expr.sheet_name else ""
            return f"Excel (SharePoint) -> {expr.file_name}{sheet}"
        elif expr.sheet_name:
            return f"Excel (SharePoint) -> [dynamic] -> {expr.sheet_name}"
        else:
            return "Excel (SharePoint) -> [dynamic]"

    if t == "excel_local":
        sheet = f" -> {expr.sheet_name}" if expr.sheet_name else ""
        return f"Excel (local) -> {expr.file_name}{sheet}"

    if t == "csv_local":
        return f"CSV (local) -> {expr.file_name}"

    if t == "web_api":
        return f"Web API -> {expr.url}"

    if t == "odata":
        tbl = f" -> {expr.table_or_view}" if expr.table_or_view else ""
        return f"OData -> {expr.url}{tbl}"

    if t == "smartsheet":
        region = f" ({expr.url})" if expr.url else ""
        return f"Smartsheet{region}"

    if t == "embedded":
        return "Embedded data"

    if t == "calc_series":
        return "Calculated series"

    if t == "table_combine":
        sources = ", ".join(expr.combine_sources) if expr.combine_sources else "?"
        return f"Combines: {sources}"

    if t == "hardcoded":
        return "Hardcoded (inline M)"

    if t == "dynamic":
        return "Dynamic M (runtime)"

    if t in ("function_def", "scalar_helper"):
        return t.replace("_", " ").title()

    if t == "powerbi_dataset":
        return "Power BI Dataset"

    if t == "dataverse":
        return f"Dataverse -> {expr.url or '?'}"

    if t == "connector_unknown":
        fn = expr.connector_fn or "unknown"
        return f"{fn} (unrecognised connector)"

    # All other new connector types — use the label dict with detail if available
    friendly = _CONNECTOR_LABELS.get(t, t.replace("_", " ").title())
    if expr.server and expr.database:
        return f"{friendly} -> {expr.server} -> {expr.database}"
    if expr.url:
        return f"{friendly} -> {expr.url}"
    if expr.entity:
        return f"{friendly} -> {expr.entity}"
    return friendly


def _resolve_param(value: str, params: dict[str, str]) -> str:
    if value.startswith("[param:") and value.endswith("]"):
        param_name = value[7:-1]
        return params.get(param_name, value)
    return value


# ---------------------------------------------------------------------------
# Chain label builder
# ---------------------------------------------------------------------------

def _build_chain_label(chain: list[str], terminal_label: str) -> str:
    if not chain:
        return terminal_label
    return " -> ".join(chain) + " -> " + terminal_label


# ---------------------------------------------------------------------------
# Core resolver
# ---------------------------------------------------------------------------

def resolve_sources(
    source_expressions: list[SourceExpression],
    m_parameters: list[MParameter],
    tables: list = None,
    manual_overrides: Optional[dict[str, str]] = None,
) -> dict[str, ResolvedSource]:
    manual_overrides = manual_overrides or {}
    tables = tables or []
    params: dict[str, str] = {p.name: p.value for p in m_parameters}
    expr_map: dict[str, SourceExpression] = {e.name: e for e in source_expressions}

    inline_map: dict[str, SourceExpression] = {}
    for tbl in tables:
        if tbl.inline_source is not None:
            inline_map[tbl.name] = tbl.inline_source

    resolved: dict[str, ResolvedSource] = {}

    # Pass 1: resolve all terminal expressions from expressions.tmdl
    for expr in source_expressions:
        if expr.source_type in _TERMINAL_TYPES:
            rs = _from_expr(expr, params, tier=1)
            if expr.name in manual_overrides:
                rs.manual_label = manual_overrides[expr.name]
                rs.label        = manual_overrides[expr.name]
            resolved[expr.name] = rs

    # Pass 2: resolve derived / custom_function from expressions.tmdl
    max_passes = 10
    for _ in range(max_passes):
        unresolved_tier2 = [
            e for e in source_expressions
            if e.name not in resolved and e.source_type in ("derived", "custom_function")
        ]
        if not unresolved_tier2:
            break
        for expr in unresolved_tier2:
            if expr.source_type == "derived":
                parent_name = expr.derived_from
                if parent_name in resolved:
                    parent = resolved[parent_name]
                    rs = _copy_resolved(expr.name, parent, tier=2)
                    rs.derived_from = parent_name
                    rs.chain = [parent_name] + parent.chain
                    rs.label = _build_chain_label([parent_name], _terminal_label(parent))
                    resolved[expr.name] = rs
                elif parent_name not in expr_map:
                    resolved[expr.name] = _unresolved(
                        expr.name, f"references '{parent_name}' which does not exist"
                    )

            elif expr.source_type == "custom_function":
                fn_name = expr.function_name
                if fn_name in resolved:
                    parent = resolved[fn_name]
                    rs = _copy_resolved(expr.name, parent, tier=2)
                    entity = expr.function_args.strip('"').split(",")[-1].strip().strip('"')
                    if entity and rs.source_type in ("dataflow_pbi", "dataflow_platform"):
                        rs.entity = entity
                        connector = "Power BI Dataflow" if rs.source_type == "dataflow_pbi" else "Power Platform Dataflow"
                        rs.label = f"{connector} -> {entity}"
                    rs.derived_from = fn_name
                    rs.chain = [fn_name]
                    resolved[expr.name] = rs
                elif fn_name not in expr_map:
                    resolved[expr.name] = _unresolved(
                        expr.name, f"calls function '{fn_name}' which is not defined in this model"
                    )

    # Pass 3: resolve inline sources from table files
    all_inline = list(inline_map.items())
    for _ in range(max_passes):
        pending = [(name, expr) for name, expr in all_inline if name not in resolved]
        if not pending:
            break
        made_progress = False
        for table_name, expr in pending:
            rs = _resolve_inline(table_name, expr, resolved, expr_map, inline_map, params)
            if rs is not None:
                if table_name in manual_overrides:
                    rs.manual_label = manual_overrides[table_name]
                    rs.label        = manual_overrides[table_name]
                resolved[table_name] = rs
                made_progress = True
        if not made_progress:
            break

    # Pass 4: anything still unresolved
    for expr in source_expressions:
        if expr.name in resolved:
            continue
        if expr.source_type == "dynamic":
            rs = _unresolved(expr.name, "Dynamic M - built at runtime")
            rs.source_type = "dynamic"
            rs.label       = "Dynamic M (runtime)"
            if expr.name in manual_overrides:
                rs.unresolved   = False
                rs.manual_label = manual_overrides[expr.name]
                rs.label        = manual_overrides[expr.name]
            resolved[expr.name] = rs
        elif expr.source_type in ("function_def", "scalar_helper"):
            resolved[expr.name] = _from_expr(expr, params, tier=1)
        else:
            resolved[expr.name] = _unresolved(
                expr.name, f"Unclassified source type: {expr.source_type}"
            )

    for table_name in inline_map:
        if table_name not in resolved:
            resolved[table_name] = _unresolved(table_name, "Inline source could not be resolved")

    return resolved


# ---------------------------------------------------------------------------
# Inline source resolver
# ---------------------------------------------------------------------------

def _resolve_inline(
    table_name: str,
    expr: SourceExpression,
    resolved: dict[str, ResolvedSource],
    expr_map: dict[str, SourceExpression],
    inline_map: dict[str, SourceExpression],
    params: dict[str, str],
) -> Optional[ResolvedSource]:
    t = expr.source_type

    if t in _TERMINAL_TYPES:
        return _from_expr(expr, params, tier=1)

    if t == "table_combine":
        return _from_expr(expr, params, tier=1)

    if t == "derived_table":
        parent_name = expr.derived_from
        if parent_name in resolved:
            parent = resolved[parent_name]
            rs = _copy_resolved(table_name, parent, tier=2)
            rs.derived_from = parent_name
            rs.chain = [parent_name] + parent.chain
            rs.label = _build_chain_label([parent_name], _terminal_label(parent))
            return rs
        if parent_name not in resolved and parent_name not in inline_map and parent_name not in expr_map:
            return _unresolved(table_name, f"references '{parent_name}' which does not exist in this model")
        return None  # retry next pass

    if t == "derived":
        parent_name = expr.derived_from
        if parent_name in resolved:
            parent = resolved[parent_name]
            rs = _copy_resolved(table_name, parent, tier=2)
            rs.derived_from = parent_name
            rs.chain = [parent_name] + parent.chain
            rs.label = _build_chain_label([parent_name], _terminal_label(parent))
            return rs
        if parent_name not in expr_map and parent_name not in inline_map:
            return _unresolved(table_name, f"references '{parent_name}' which does not exist")
        return None  # retry

    return _unresolved(table_name, f"Unrecognised inline source type: {t}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _terminal_label(rs: ResolvedSource) -> str:
    return rs.label


def _from_expr(expr: SourceExpression, params: dict[str, str], tier: int) -> ResolvedSource:
    rs = ResolvedSource(
        expression_name=expr.name,
        source_type=expr.source_type,
        resolution_tier=tier,
        workspace_id=expr.workspace_id,
        dataflow_id=expr.dataflow_id,
        entity=expr.entity,
        server=_resolve_param(expr.server, params),
        database=_resolve_param(expr.database, params),
        schema=expr.schema,
        table_or_view=expr.table_or_view,
        native_query=expr.native_query,
        dsn=expr.dsn,
        sharepoint_url=expr.sharepoint_url,
        file_name=expr.file_name,
        sheet_name=expr.sheet_name,
        url=expr.url,
        physical_tables=list(expr.physical_tables),
    )
    rs.label = _build_label(expr, params)
    return rs


def _copy_resolved(name: str, parent: ResolvedSource, tier: int) -> ResolvedSource:
    return ResolvedSource(
        expression_name=name,
        source_type=parent.source_type,
        resolution_tier=tier,
        workspace_id=parent.workspace_id,
        dataflow_id=parent.dataflow_id,
        entity=parent.entity,
        server=parent.server,
        database=parent.database,
        schema=parent.schema,
        table_or_view=parent.table_or_view,
        native_query=parent.native_query,
        dsn=parent.dsn,
        sharepoint_url=parent.sharepoint_url,
        file_name=parent.file_name,
        sheet_name=parent.sheet_name,
        url=parent.url,
        physical_tables=list(parent.physical_tables),
        label=parent.label,
    )


def _unresolved(name: str, reason: str) -> ResolvedSource:
    return ResolvedSource(
        expression_name=name,
        source_type="unresolved",
        resolution_tier=3,
        label=f"Unresolved - {reason}",
        unresolved=True,
        unresolved_reason=reason,
    )


# ---------------------------------------------------------------------------
# Convenience: get resolved source for a table
# ---------------------------------------------------------------------------

def get_table_source(
    table,
    resolved: dict[str, ResolvedSource],
) -> Optional[ResolvedSource]:
    if table.source_ref:
        return resolved.get(table.source_ref)
    if table.inline_source is not None:
        return resolved.get(table.name)
    return None


def list_unresolved(resolved: dict[str, ResolvedSource]) -> list[ResolvedSource]:
    return [rs for rs in resolved.values() if rs.unresolved]
