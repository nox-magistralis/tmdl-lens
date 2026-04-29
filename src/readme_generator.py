"""
readme_generator.py — Markdown README generator for tmdl-lens.

Takes a parsed SemanticModel and resolved sources dict and produces
a structured README.md for each Power BI report.
"""

from datetime import date
from src.tmdl_parser import SemanticModel, Table
from src.source_resolver import ResolvedSource, get_table_source


# ---------------------------------------------------------------------------
# Data type display map
# ---------------------------------------------------------------------------

_DTYPE = {
    "string":     "Text",
    "int64":      "Integer",
    "double":     "Decimal",
    "decimal":    "Decimal",
    "dateTime":   "Date/Time",
    "boolean":    "True/False",
    "calculated": "Calculated",
    "unknown":    "—",
}

def _dtype(raw: str) -> str:
    return _DTYPE.get(raw, raw)


# ---------------------------------------------------------------------------
# Source type display map
# ---------------------------------------------------------------------------

_SOURCE_TYPE_LABEL = {
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
    "table_combine":     "Combined Queries",
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
    "powerbi_dataset":   "Power BI Dataset",
    "dataverse":         "Dataverse",
    "azure_devops":      "Azure DevOps",
    "dynamics_fo":       "Dynamics 365 Finance & Operations",
    "google_sheets":     "Google Sheets",
    "quickbooks":        "QuickBooks",
    "github":            "GitHub",
    "connector_unknown": "Unknown Connector",
    "derived":           "Derived Query",
    "derived_table":     "Derived Query",
    "dynamic":           "Dynamic M",
    "unresolved":        "Unresolved",
    "function_def":      "Helper Function",
    "scalar_helper":     "Scalar Helper",
}

def _source_type_label(source_type: str) -> str:
    return _SOURCE_TYPE_LABEL.get(source_type, source_type.replace("_", " ").title())


def _source_label(rs: ResolvedSource) -> str:
    """
    Returns the display string for the Source column in the Data Sources table.
    Uses rs.label which already contains the full chain (e.g. 'FVInput -> Smartsheet (US)').
    Falls back to manual_label if set. Returns '-' for scalar/helper types.
    """
    if rs.manual_label:
        return rs.manual_label
    # Non-source types return '-' regardless of unresolved status
    if rs.source_type in ("scalar_helper", "function_def", "embedded", "hardcoded",
                           "calc_series", "dynamic"):
        return "-"
    if rs.unresolved:
        return rs.unresolved_reason or "Unresolved"
    label = rs.label or "-"
    if rs.source_type in ("dataflow_pbi", "dataflow_platform"):
        if rs.entity:
            if rs.chain:
                return label
            return rs.entity
        return label
    return label


# ---------------------------------------------------------------------------
# Table type display map
# ---------------------------------------------------------------------------

_TABLE_TYPE_LABEL = {
    "calculated":      "Calculated (DAX)",
    "field_parameter": "Field Parameter",
    "measures_only":   "Measures",
    "calc_group":      "Calculation Group",
}

def _table_type_label(table_type: str) -> str:
    return _TABLE_TYPE_LABEL.get(table_type, "Loaded")


# ---------------------------------------------------------------------------
# Auto date table filter
# Power BI auto-generates these hidden tables and their relationships.
# They add noise to the output and are suppressed.
# ---------------------------------------------------------------------------

def _is_auto_date_table(name: str) -> bool:
    return name.startswith("LocalDateTable_") or name.startswith("DateTableTemplate_")


# ---------------------------------------------------------------------------
# Section helpers
# ---------------------------------------------------------------------------

def _model_summary(
    loaded_tables: list[Table],
    staging_tables: list[Table],
    support_tables: list[Table],
    model: SemanticModel,
) -> str:
    n_loaded   = len(loaded_tables)
    n_staging  = len(staging_tables)
    n_meas     = sum(len(t.measures) for t in model.tables)
    visible_rels = [
        r for r in model.relationships
        if not _is_auto_date_table(r.from_table) and not _is_auto_date_table(r.to_table)
    ]
    n_rels = len(visible_rels)

    parts = [f"{n_loaded} loaded {'table' if n_loaded == 1 else 'tables'}"]
    if support_tables:
        labels = []
        calc   = [t for t in support_tables if t.table_type == "calculated"]
        fp     = [t for t in support_tables if t.table_type == "field_parameter"]
        mo     = [t for t in support_tables if t.table_type == "measures_only"]
        cg     = [t for t in support_tables if t.table_type == "calc_group"]
        if calc: labels.append(f"{len(calc)} calculated {'table' if len(calc) == 1 else 'tables'}")
        if fp:   labels.append(f"{len(fp)} field {'parameter' if len(fp) == 1 else 'parameters'}")
        if mo:   labels.append(f"{len(mo)} measures-only {'table' if len(mo) == 1 else 'tables'}")
        if cg:   labels.append(f"{len(cg)} calculation {'group' if len(cg) == 1 else 'groups'}")
        if labels:
            parts.append(", ".join(labels))
    if n_staging:
        parts.append(f"{n_staging} not loaded")
    parts.append(f"{n_meas} {'measure' if n_meas == 1 else 'measures'}")
    parts.append(f"{n_rels} {'relationship' if n_rels == 1 else 'relationships'}")

    return "This model contains " + ", ".join(parts) + "."


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _overview_section(config: dict) -> str:
    owner   = config.get("owner", "—")
    team    = config.get("team", "—")
    refresh = config.get("refresh_schedule", "—")
    today   = date.today().strftime("%d %B %Y")

    lines = [
        "## Overview",
        "",
        "| Property | Value |",
        "|---|---|",
        f"| **Owner** | {owner} |",
        f"| **Team** | {team} |",
        f"| **Refresh Schedule** | {refresh} |",
        f"| **Last Generated** | {today} |",
        "",
        "---",
        "",
    ]
    return "\n".join(lines)


def _data_sources_section(
    loaded_tables: list[Table],
    staging_tables: list[Table],
    support_tables: list[Table],
    resolved: dict[str, ResolvedSource],
    model: SemanticModel,
) -> str:
    lines = ["## 1. Data Sources", ""]
    lines += [_model_summary(loaded_tables, staging_tables, support_tables, model), ""]

    if loaded_tables:
        lines += [
            "| Table | Source Type | Source |",
            "|---|---|---|",
        ]
        for t in loaded_tables:
            rs = get_table_source(t, resolved)
            if rs:
                src_type = _source_type_label(rs.source_type)
                label    = _source_label(rs)
            else:
                src_type = "—"
                label    = "—"
            lines.append(f"| `{t.name}` | {src_type} | {label} |")
        lines.append("")
    else:
        lines += ["*No loaded tables found.*", ""]

    if support_tables:
        lines += [
            "### Support Tables",
            "",
            "| Table | Type |",
            "|---|---|",
        ]
        for t in support_tables:
            lines.append(f"| `{t.name}` | {_table_type_label(t.table_type)} |")
        lines.append("")

    if staging_tables:
        lines += [
            "### Not Loaded",
            "",
            "> These tables have `enableLoad = false` and are not visible in the report.",
            "> They are typically used as intermediate query steps.",
            "",
            "| Table | Source Type | Source |",
            "|---|---|---|",
        ]
        for t in staging_tables:
            rs = get_table_source(t, resolved)
            if rs:
                src_type = _source_type_label(rs.source_type)
                label    = _source_label(rs)
            else:
                src_type = "—"
                label    = "—"
            lines.append(f"| `{t.name}` | {src_type} | {label} |")
        lines.append("")
    else:
        lines += ["### Not Loaded", "", "*None.*", ""]

    lines += ["---", ""]
    return "\n".join(lines)


def _table_detail_block(
    table: Table,
    resolved: dict[str, ResolvedSource],
    include_dax: bool,
) -> str:
    lines = [f"### `{table.name}`", ""]

    rs = get_table_source(table, resolved)

    if rs:
        src_type_display = _source_type_label(rs.source_type)
        lines.append(f"**Source:** {src_type_display}  ")
        if rs.source_type in ("dataflow_pbi", "dataflow_platform") and rs.entity:
            lines.append(f"**Entity:** `{rs.entity}`  ")
        if rs.source_type in ("sql", "sql_native_query"):
            if rs.schema and rs.table_or_view:
                lines.append(f"**Table:** `{rs.schema}.{rs.table_or_view}`  ")
            if rs.server:
                lines.append(f"**Server:** `{rs.server}`  ")
            if rs.database:
                lines.append(f"**Database:** `{rs.database}`  ")
        if rs.source_type in ("oracle", "mysql", "postgresql", "db2", "sap_hana", "snowflake"):
            if rs.server:
                lines.append(f"**Server:** `{rs.server}`  ")
            if rs.database:
                lines.append(f"**Database:** `{rs.database}`  ")
        if rs.source_type == "teradata":
            if rs.server:
                lines.append(f"**Server:** `{rs.server}`  ")
        if rs.source_type == "databricks":
            if rs.server:
                lines.append(f"**Host:** `{rs.server}`  ")
        if rs.source_type == "dataverse":
            if rs.url:
                lines.append(f"**Environment URL:** `{rs.url}`  ")
        if rs.source_type in ("azure_devops", "dynamics_fo", "google_sheets", "quickbooks", "github"):
            if rs.url:
                lines.append(f"**URL:** `{rs.url}`  ")
        if rs.source_type == "odbc" and rs.dsn:
            lines.append(f"**DSN:** `{rs.dsn}`  ")
        if rs.source_type in ("sharepoint_files", "sharepoint_tables", "excel_sharepoint") and rs.sharepoint_url:
            lines.append(f"**SharePoint URL:** `{rs.sharepoint_url}`  ")
        if rs.source_type in ("excel_local", "csv_local", "excel_sharepoint") and rs.file_name:
            lines.append(f"**File:** `{rs.file_name}`  ")
        if rs.source_type in ("excel_local", "excel_sharepoint") and rs.sheet_name:
            lines.append(f"**Sheet:** `{rs.sheet_name}`  ")
        if rs.source_type in ("web_api", "odata") and rs.url:
            lines.append(f"**URL:** `{rs.url}`  ")
        if rs.chain:
            lines.append(f"**Chain:** `{rs.label}`  ")
        if rs.unresolved:
            lines.append(f"**⚠ Unresolved:** {rs.unresolved_reason}  ")
    elif table.table_type == "calculated":
        lines.append("**Source:** Calculated (DAX)  ")
        if include_dax and table.dax_partition:
            lines += ["", "```dax", table.dax_partition, "```"]
    elif table.table_type == "field_parameter":
        lines.append("**Source:** Field Parameter  ")
    elif table.table_type == "measures_only":
        lines.append("**Source:** Measures only - no data source  ")

    if not table.is_loaded:
        lines += ["", "> ⚠ Not loaded (`enableLoad = false`)."]

    lines.append("")

    visible_cols = [c for c in table.columns if not c.is_hidden and not c.is_calculated]
    if visible_cols:
        lines += ["**Columns**", "", "| Column | Type |", "|---|---|"]
        for col in visible_cols:
            lines.append(f"| `{col.name}` | {_dtype(col.data_type)} |")
        lines.append("")

    hidden_cols = [c for c in table.columns if c.is_hidden and not c.is_calculated]
    if hidden_cols:
        details = ", ".join(f"`{c.name}`" for c in hidden_cols)
        lines += [f"**Hidden Columns:** {details}  ", ""]

    calc_cols = [c for c in table.columns if c.is_calculated]
    if calc_cols:
        lines += ["**Calculated Columns**", ""]
        for col in calc_cols:
            if include_dax and col.dax_expression:
                lines += [f"- **`{col.name}`**", "  ```dax", f"  {col.dax_expression}", "  ```"]
            else:
                lines.append(f"- `{col.name}`")
        lines.append("")

    if table.calculation_items:
        lines += ["**Calculation Items**", "", "| Item | Ordinal | Format String |", "|---|---|---|"]
        for item in table.calculation_items:
            fmt = f"`{item.format_string_expression}`" if item.format_string_expression else "—"
            lines.append(f"| `{item.name}` | {item.ordinal} | {fmt} |")
        lines.append("")
        if include_dax:
            lines += ["**Item DAX**", ""]
            for item in table.calculation_items:
                lines += [f"**`{item.name}`**", "```dax", item.dax_expression, "```", ""]

    if table.measures:
        lines += ["**Measures**", "", "| Measure | Format | Description |", "|---|---|---|"]
        for m in table.measures:
            fmt  = f"`{m.format_string}`" if m.format_string else "—"
            desc = m.description or "—"
            lines.append(f"| `{m.name}` | {fmt} | {desc} |")
        if include_dax:
            lines += ["", "**Measure DAX**", ""]
            for m in table.measures:
                if not m.dax_expression.strip():
                    continue
                lines += [f"**`{m.name}`**", "```dax", m.dax_expression, "```", ""]

    return "\n".join(lines)


def _table_details_section(
    loaded_tables: list[Table],
    support_tables: list[Table],
    resolved: dict[str, ResolvedSource],
    include_dax: bool,
) -> str:
    lines = ["## 2. Table Details", ""]
    calc_groups = [t for t in support_tables if t.table_type == "calc_group"]
    all_tables = loaded_tables + calc_groups
    if all_tables:
        for t in all_tables:
            lines.append(_table_detail_block(t, resolved, include_dax))
            lines += ["---", ""]
    else:
        lines += ["*No loaded tables.*", "", "---", ""]
    return "\n".join(lines)


def _measures_section(tables: list[Table], include_dax: bool) -> str:
    all_measures = [(t.name, m) for t in tables for m in t.measures]
    lines = ["## 3. Measures", ""]

    if not all_measures:
        lines += ["*No measures defined in this model.*", "", "---", ""]
        return "\n".join(lines)

    folders: dict[str, list[tuple]] = {}
    for table_name, m in all_measures:
        folder = m.display_folder or "General"
        folders.setdefault(folder, []).append((table_name, m))

    for folder in sorted(folders.keys()):
        lines += [f"### {folder}", "", "| Measure | Table | Format | Description |", "|---|---|---|---|"]
        for table_name, m in folders[folder]:
            fmt  = f"`{m.format_string}`" if m.format_string else "—"
            desc = m.description or "—"
            lines.append(f"| `{m.name}` | `{table_name}` | {fmt} | {desc} |")
        lines.append("")
        if include_dax:
            for _, m in folders[folder]:
                if not m.dax_expression.strip():
                    continue
                lines += [f"**`{m.name}`**", "```dax", m.dax_expression, "```", ""]

    lines += ["---", ""]
    return "\n".join(lines)


def _relationships_section(model: SemanticModel) -> str:
    lines = ["## 4. Relationships", ""]

    visible = [
        r for r in model.relationships
        if not _is_auto_date_table(r.from_table) and not _is_auto_date_table(r.to_table)
    ]

    if not visible:
        lines += ["*No relationships defined in this model.*", "", "---", ""]
        return "\n".join(lines)

    active   = [r for r in visible if r.is_active]
    inactive = [r for r in visible if not r.is_active]

    if active:
        lines += [
            "| From Table | From Column | To Table | To Column | Cardinality |",
            "|---|---|---|---|---|",
        ]
        for r in active:
            lines.append(
                f"| `{r.from_table}` | `{r.from_column}` | `{r.to_table}` | `{r.to_column}` | {r.cardinality or '—'} |"
            )
        lines.append("")

    if inactive:
        lines += [
            "**Inactive Relationships**", "",
            "| From Table | From Column | To Table | To Column |",
            "|---|---|---|---|",
        ]
        for r in inactive:
            lines.append(
                f"| `{r.from_table}` | `{r.from_column}` | `{r.to_table}` | `{r.to_column}` |"
            )
        lines.append("")

    lines += ["---", ""]
    return "\n".join(lines)


def _build_param_usage_map(model: SemanticModel) -> dict[str, list[str]]:
    usage: dict[str, list[str]] = {p.name: [] for p in model.m_parameters}
    param_names = set(usage.keys())
    for expr in model.source_expressions:
        for field_val in (expr.server, expr.database, expr.url, expr.file_name, expr.sharepoint_url, expr.dsn):
            if not field_val:
                continue
            for pname in param_names:
                if f"[param:{pname}]" in field_val:
                    if expr.name not in usage[pname]:
                        usage[pname].append(expr.name)
    return usage


def _security_roles_section(model: SemanticModel) -> str:
    lines = ["## 5. Security Roles", ""]

    if not model.security_roles:
        lines += ["*No security roles defined.*", "", "---", ""]
        return "\n".join(lines)

    lines += ["| Role | Table | Filter | Dynamic |", "|---|---|---|---|"]
    for role in model.security_roles:
        if not role.table_filters:
            dynamic_label = f"Yes ({role.dynamic_function})" if role.is_dynamic else "No"
            lines.append(f"| `{role.name}` | — | — | {dynamic_label} |")
        else:
            for i, tf in enumerate(role.table_filters):
                role_cell     = f"`{role.name}`" if i == 0 else ""
                dynamic_label = (f"Yes ({role.dynamic_function})" if role.is_dynamic else "No") if i == 0 else ""
                lines.append(f"| {role_cell} | `{tf.table}` | `{tf.dax_filter}` | {dynamic_label} |")

    lines += ["", "---", ""]
    return "\n".join(lines)


def _m_parameters_section(model: SemanticModel) -> str:
    lines = ["## 6. M Parameters", ""]

    if not model.m_parameters:
        lines += ["*No M parameters defined.*", "", "---", ""]
        return "\n".join(lines)

    usage_map = _build_param_usage_map(model)
    lines += ["| Parameter | Type | Value | Used By |", "|---|---|---|---|"]
    for p in model.m_parameters:
        used_by   = usage_map.get(p.name, [])
        used_cell = ", ".join(f"`{e}`" for e in used_by) if used_by else "—"
        val_cell  = f"`{p.value}`" if p.value.strip() else "—"
        lines.append(f"| `{p.name}` | {p.param_type} | {val_cell} | {used_cell} |")

    lines += [
        "",
        "> *Only direct parameter references in connector calls are shown.",
        "> Parameters used in conditional logic or computed expressions may not appear here.*",
        "",
        "---",
        "",
    ]
    return "\n".join(lines)


def _unresolved_section(resolved: dict[str, ResolvedSource]) -> str:
    unresolved = [rs for rs in resolved.values() if rs.unresolved]
    if not unresolved:
        return ""
    lines = [
        "## ⚠ Unresolved Sources",
        "",
        "The following sources could not be resolved statically.",
        "Use tmdl-lens to provide a manual label for each.",
        "",
        "| Expression | Reason |",
        "|---|---|",
    ]
    for rs in unresolved:
        lines.append(f"| `{rs.expression_name}` | {rs.unresolved_reason} |")
    lines += ["", "---", ""]
    return "\n".join(lines)


def _statistics_section(
    model: SemanticModel,
    loaded_tables: list[Table],
    support_tables: list[Table],
    staging_tables: list[Table],
) -> str:
    calc      = [t for t in support_tables if t.table_type == "calculated"]
    fp        = [t for t in support_tables if t.table_type == "field_parameter"]
    mo        = [t for t in support_tables if t.table_type == "measures_only"]
    cg        = [t for t in support_tables if t.table_type == "calc_group"]
    all_meas  = [m for t in model.tables for m in t.measures]
    calc_cols = [c for t in model.tables for c in t.columns if c.is_calculated]
    visible_rels = [
        r for r in model.relationships
        if not _is_auto_date_table(r.from_table) and not _is_auto_date_table(r.to_table)
    ]

    def names(lst):
        return ", ".join(f"`{t.name}`" for t in lst) if lst else "—"

    lines = [
        "## 7. Model Statistics",
        "",
        "| Category | Count | Items |",
        "|---|---|---|",
        f"| Loaded Tables | {len(loaded_tables)} | {names(loaded_tables)} |",
        f"| Calculated Tables | {len(calc)} | {names(calc)} |",
        f"| Field Parameters | {len(fp)} | {names(fp)} |",
        f"| Measures-Only Tables | {len(mo)} | {names(mo)} |",
        f"| Calculation Groups | {len(cg)} | {names(cg)} |",
        f"| Not Loaded | {len(staging_tables)} | {names(staging_tables)} |",
        f"| Relationships | {len(visible_rels)} | — |",
        f"| Measures | {len(all_meas)} | — |",
        f"| Calculated Columns | {len(calc_cols)} | — |",
        "",
        "---",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# HTML renderer
# ---------------------------------------------------------------------------

_HTML_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    font-size: 14px; line-height: 1.6;
    background: #f8f9fb; color: #1e2330;
    padding: 32px 24px;
}
.container { max-width: 1100px; margin: 0 auto; }
h1 { font-size: 26px; font-weight: 700; color: #0f1520; margin-bottom: 6px; }
.subtitle { font-size: 13px; color: #7b8499; margin-bottom: 32px; }
h2 { font-size: 17px; font-weight: 700; color: #1e2330; margin: 36px 0 14px;
     padding-bottom: 6px; border-bottom: 2px solid #e2e6f0; }
h3 { font-size: 14px; font-weight: 600; color: #2e3548; margin: 20px 0 8px; }
h4 { font-size: 13px; font-weight: 600; color: #4a5068; margin: 14px 0 6px; }
table { width: 100%; border-collapse: collapse; margin-bottom: 16px; font-size: 13px; }
th { background: #eef0f7; color: #3d4464; font-weight: 600;
     padding: 8px 12px; text-align: left; border: 1px solid #dde1ee; }
td { padding: 7px 12px; border: 1px solid #e8eaf2; vertical-align: top; }
tr:nth-child(even) td { background: #f4f5fb; }
code { font-family: 'Cascadia Code', 'Consolas', monospace;
       font-size: 12px; background: #eef0f7; color: #2e3548;
       padding: 1px 5px; border-radius: 3px; }
pre { background: #1e2330; color: #c8d0e8;
      font-family: 'Cascadia Code', 'Consolas', monospace;
      font-size: 12px; padding: 14px 16px; border-radius: 6px;
      overflow-x: auto; margin: 8px 0 14px; white-space: pre-wrap; }
pre code { background: none; color: inherit; padding: 0; }
.overview-table td:first-child { font-weight: 600; width: 180px; color: #3d4464; }
.section-note { font-size: 12px; color: #7b8499; margin-bottom: 10px;
                padding: 8px 12px; background: #f0f2fa;
                border-left: 3px solid #c5cae0; border-radius: 0 4px 4px 0; }
.footer { margin-top: 40px; font-size: 12px; color: #9aa3b8;
          border-top: 1px solid #e2e6f0; padding-top: 12px; }
.empty { color: #9aa3b8; font-style: italic; font-size: 13px; }
"""


def _esc(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _html_table(headers: list[str], rows: list[list[str]], css_class: str = "") -> str:
    cls = f' class="{css_class}"' if css_class else ""
    th_cells = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    body_rows = "".join(f"<tr>{''.join(f'<td>{_esc(cell)}</td>' for cell in row)}</tr>" for row in rows)
    return f"<table{cls}><thead><tr>{th_cells}</tr></thead><tbody>{body_rows}</tbody></table>"


def _code(text: str) -> str:
    return f"<code>{_esc(text)}</code>"


def _pre(text: str) -> str:
    return f"<pre><code>{_esc(text)}</code></pre>"


def generate_html(
    model: SemanticModel,
    resolved: dict[str, ResolvedSource],
    config: dict,
) -> str:
    report_name = config.get("report_name", model.report_name)
    include_dax = config.get("include_dax", True)
    today       = date.today().strftime("%d %B %Y")

    support_types = {"calculated", "field_parameter", "measures_only", "calc_group"}
    loaded  = [t for t in model.tables if t.is_loaded and t.table_type not in support_types]
    support = [t for t in model.tables if t.is_loaded and t.table_type in support_types]
    staging = [t for t in model.tables if not t.is_loaded]

    body = [f'<div class="container">',
            f'<h1>{_esc(report_name)}</h1>',
            f'<div class="subtitle">Generated by tmdl-lens &middot; {today}</div>']

    body.append('<h2>Overview</h2>')
    body.append(_html_table(["Property", "Value"], [
        ["Owner",            _esc(config.get("owner", "-") or "-")],
        ["Team",             _esc(config.get("team", "-") or "-")],
        ["Refresh Schedule", _esc(config.get("refresh_schedule", "-") or "-")],
        ["Last Generated",   today],
    ], "overview-table"))

    body.append('<h2>1. Data Sources</h2>')
    body.append(f'<p>{_esc(_model_summary(loaded, staging, support, model))}</p>')
    if loaded:
        rows = []
        for t in loaded:
            rs = get_table_source(t, resolved)
            src_type = _source_type_label(rs.source_type) if rs else "-"
            label    = _source_label(rs) if rs else "-"
            rows.append([_code(t.name), _esc(src_type), _esc(label)])
        body.append(_html_table(["Table", "Source Type", "Source"], rows))
    if support:
        body.append('<h3>Support Tables</h3>')
        body.append(_html_table(["Table", "Type"],
            [[_code(t.name), _esc(_table_type_label(t.table_type))] for t in support]))
    body.append('<h3>Not Loaded</h3>')
    if staging:
        rows = []
        for t in staging:
            rs = get_table_source(t, resolved)
            src_type = _source_type_label(rs.source_type) if rs else "-"
            label    = _source_label(rs) if rs else "-"
            rows.append([_code(t.name), _esc(src_type), _esc(label)])
        body.append(_html_table(["Table", "Source Type", "Source"], rows))
    else:
        body.append('<p class="empty">None.</p>')

    body.append('<h2>2. Table Details</h2>')
    calc_groups = [t for t in support if t.table_type == "calc_group"]
    for t in loaded + calc_groups:
        body.append(f'<h3>{_code(t.name)}</h3>')
        rs = get_table_source(t, resolved)
        if rs:
            body.append(f'<p><strong>Source:</strong> {_esc(_source_type_label(rs.source_type))}</p>')
            if rs.label and rs.label != _source_type_label(rs.source_type):
                body.append(f'<p><strong>Detail:</strong> {_esc(rs.label)}</p>')
        elif t.table_type == "calculated":
            body.append('<p><strong>Source:</strong> Calculated (DAX)</p>')
            if include_dax and t.dax_partition:
                body.append(_pre(t.dax_partition))
        visible_cols = [c for c in t.columns if not c.is_hidden and not c.is_calculated]
        if visible_cols:
            body.append('<h4>Columns</h4>')
            body.append(_html_table(["Column", "Type"],
                [[_code(c.name), _esc(_dtype(c.data_type))] for c in visible_cols]))
        if t.calculation_items:
            body.append('<h4>Calculation Items</h4>')
            rows = [[_code(i.name), str(i.ordinal),
                     _code(i.format_string_expression) if i.format_string_expression else "-"]
                    for i in t.calculation_items]
            body.append(_html_table(["Item", "Ordinal", "Format String"], rows))
            if include_dax:
                for item in t.calculation_items:
                    body.append(f'<h4>{_code(item.name)}</h4>')
                    body.append(_pre(item.dax_expression))
        if t.measures:
            body.append('<h4>Measures</h4>')
            rows = [[_code(m.name),
                     _code(m.format_string) if m.format_string else "-",
                     _esc(m.description) if m.description else "-"]
                    for m in t.measures]
            body.append(_html_table(["Measure", "Format", "Description"], rows))
            if include_dax:
                for m in t.measures:
                    body.append(f'<h4>{_code(m.name)}</h4>')
                    body.append(_pre(m.dax_expression))

    body.append('<h2>3. Measures</h2>')
    all_measures = [(t.name, m) for t in model.tables for m in t.measures]
    if not all_measures:
        body.append('<p class="empty">No measures defined in this model.</p>')
    else:
        folders: dict[str, list] = {}
        for table_name, m in all_measures:
            folders.setdefault(m.display_folder or "General", []).append((table_name, m))
        for folder in sorted(folders.keys()):
            body.append(f'<h3>{_esc(folder)}</h3>')
            rows = [[_code(m.name), _code(tn),
                     _code(m.format_string) if m.format_string else "-",
                     _esc(m.description) if m.description else "-"]
                    for tn, m in folders[folder]]
            body.append(_html_table(["Measure", "Table", "Format", "Description"], rows))
            if include_dax:
                for _, m in folders[folder]:
                    body.append(f'<h4>{_code(m.name)}</h4>')
                    body.append(_pre(m.dax_expression))

    body.append('<h2>4. Relationships</h2>')
    visible_rels = [
        r for r in model.relationships
        if not _is_auto_date_table(r.from_table) and not _is_auto_date_table(r.to_table)
    ]
    if not visible_rels:
        body.append('<p class="empty">No relationships defined in this model.</p>')
    else:
        active   = [r for r in visible_rels if r.is_active]
        inactive = [r for r in visible_rels if not r.is_active]
        if active:
            body.append(_html_table(
                ["From Table", "From Column", "To Table", "To Column", "Cardinality"],
                [[_code(r.from_table), _code(r.from_column),
                  _code(r.to_table),   _code(r.to_column), _esc(r.cardinality or "-")]
                 for r in active]))
        if inactive:
            body.append('<h3>Inactive Relationships</h3>')
            body.append(_html_table(
                ["From Table", "From Column", "To Table", "To Column"],
                [[_code(r.from_table), _code(r.from_column),
                  _code(r.to_table),   _code(r.to_column)]
                 for r in inactive]))

    body.append('<h2>5. Security Roles</h2>')
    if not model.security_roles:
        body.append('<p class="empty">No security roles defined.</p>')
    else:
        rows = []
        for role in model.security_roles:
            if not role.table_filters:
                dyn = f"Yes ({_esc(role.dynamic_function)})" if role.is_dynamic else "No"
                rows.append([_code(role.name), "-", "-", dyn])
            else:
                for i, tf in enumerate(role.table_filters):
                    role_cell = _code(role.name) if i == 0 else ""
                    dyn = (f"Yes ({_esc(role.dynamic_function)})" if role.is_dynamic else "No") if i == 0 else ""
                    rows.append([role_cell, _code(tf.table), _code(tf.dax_filter), dyn])
        body.append(_html_table(["Role", "Table", "Filter", "Dynamic"], rows))

    body.append('<h2>6. M Parameters</h2>')
    if not model.m_parameters:
        body.append('<p class="empty">No M parameters defined.</p>')
    else:
        usage_map = _build_param_usage_map(model)
        rows = [[_code(p.name), _esc(p.param_type), _code(p.value),
                 ", ".join(_code(e) for e in usage_map.get(p.name, [])) or "-"]
                for p in model.m_parameters]
        body.append(_html_table(["Parameter", "Type", "Value", "Used By"], rows))
        body.append('<p class="section-note">Only direct parameter references in connector calls are shown.</p>')

    unresolved = [rs for rs in resolved.values() if rs.unresolved]
    if unresolved:
        body.append('<h2>&#9888; Unresolved Sources</h2>')
        body.append('<p>The following sources could not be resolved statically.</p>')
        body.append(_html_table(["Expression", "Reason"],
            [[_code(rs.expression_name), _esc(rs.unresolved_reason)] for rs in unresolved]))

    body.append('<h2>7. Model Statistics</h2>')
    calc      = [t for t in support if t.table_type == "calculated"]
    fp        = [t for t in support if t.table_type == "field_parameter"]
    mo        = [t for t in support if t.table_type == "measures_only"]
    cg        = [t for t in support if t.table_type == "calc_group"]
    all_meas  = [m for t in model.tables for m in t.measures]
    calc_cols = [c for t in model.tables for c in t.columns if c.is_calculated]
    def _names(lst): return ", ".join(_code(t.name) for t in lst) if lst else "-"
    body.append(_html_table(["Category", "Count", "Items"], [
        ["Loaded Tables",        str(len(loaded)),               _names(loaded)],
        ["Calculated Tables",    str(len(calc)),                 _names(calc)],
        ["Field Parameters",     str(len(fp)),                   _names(fp)],
        ["Measures-Only Tables", str(len(mo)),                   _names(mo)],
        ["Calculation Groups",   str(len(cg)),                   _names(cg)],
        ["Not Loaded",           str(len(staging)),              _names(staging)],
        ["Relationships",        str(len(visible_rels)),         "-"],
        ["Measures",             str(len(all_meas)),             "-"],
        ["Calculated Columns",   str(len(calc_cols)),            "-"],
    ]))

    body.append(f'<div class="footer">Generated by tmdl-lens &middot; {today}</div>')
    body.append('</div>')

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_esc(report_name)}</title>
<style>{_HTML_CSS}</style>
</head>
<body>
{chr(10).join(body)}
</body>
</html>
"""


def generate_readme(
    model: SemanticModel,
    resolved: dict[str, ResolvedSource],
    config: dict,
) -> str:
    report_name = config.get("report_name", model.report_name)
    include_dax = config.get("include_dax", True)

    support_types = {"calculated", "field_parameter", "measures_only", "calc_group"}
    loaded   = [t for t in model.tables if t.is_loaded and t.table_type not in support_types]
    support  = [t for t in model.tables if t.is_loaded and t.table_type in support_types]
    staging  = [t for t in model.tables if not t.is_loaded]

    sections = [
        f"# {report_name}\n",
        _overview_section(config),
        _data_sources_section(loaded, staging, support, resolved, model),
        _table_details_section(loaded, support, resolved, include_dax),
        _measures_section(model.tables, include_dax),
        _relationships_section(model),
        _security_roles_section(model),
        _m_parameters_section(model),
    ]

    unresolved = _unresolved_section(resolved)
    if unresolved:
        sections.append(unresolved)

    sections.append(_statistics_section(model, loaded, support, staging))

    today = date.today().strftime("%d %B %Y")
    sections.append(f"*Generated by tmdl-lens · {today}*\n")

    return "\n".join(sections)
