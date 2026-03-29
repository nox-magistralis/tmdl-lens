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
    "sharepoint_files":  "SharePoint Files",
    "sharepoint_tables": "SharePoint List",
    "excel_sharepoint":  "Excel (SharePoint)",
    "excel_local":       "Excel (Local)",
    "csv_local":         "CSV (Local)",
    "web_api":           "Web API",
    "odata":             "OData",
    "hardcoded":         "Hardcoded (Inline M)",
    "derived":           "Derived Query",
    "dynamic":           "Dynamic M",
    "unresolved":        "Unresolved",
    "function_def":      "Helper Function",
    "scalar_helper":     "Scalar Helper",
}

def _source_type_label(source_type: str) -> str:
    return _SOURCE_TYPE_LABEL.get(source_type, source_type.replace("_", " ").title())


def _source_detail(rs: ResolvedSource) -> str:
    """
    Returns the most useful identifying detail for a resolved source,
    without repeating the connector name. Used in Section 1 table.
    """
    t = rs.source_type
    if t in ("dataflow_pbi", "dataflow_platform"):
        return rs.entity or "-"
    if t in ("sql", "sql_native_query"):
        parts = []
        if rs.server:   parts.append(rs.server)
        if rs.database: parts.append(rs.database)
        if rs.schema and rs.table_or_view:
            parts.append(f"{rs.schema}.{rs.table_or_view}")
        return " / ".join(parts) if parts else "-"
    if t == "odbc":
        if rs.schema and rs.table_or_view:
            return f"{rs.dsn} / {rs.schema}.{rs.table_or_view}"
        return rs.dsn or "-"
    if t in ("sharepoint_files", "sharepoint_tables", "excel_sharepoint"):
        parts = []
        if rs.sharepoint_url: parts.append(rs.sharepoint_url)
        if rs.file_name:      parts.append(rs.file_name)
        if rs.sheet_name:     parts.append(rs.sheet_name)
        if rs.table_or_view:  parts.append(rs.table_or_view)
        return " / ".join(parts) if parts else "-"
    if t in ("excel_local", "csv_local"):
        detail = rs.file_name or "-"
        if rs.sheet_name:
            detail += f" / {rs.sheet_name}"
        return detail
    if t in ("web_api", "odata"):
        return rs.url or "-"
    if t == "hardcoded":
        return "Inline M"
    if t == "dynamic":
        return rs.manual_label or "Runtime URL - manual label required"
    if rs.unresolved:
        return rs.manual_label or "Unresolved"
    return "-"


# ---------------------------------------------------------------------------
# Table type display map
# Only structurally confirmed types get a specific label.
# Everything else is "Loaded" — generic and always accurate.
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
# Section helpers
# ---------------------------------------------------------------------------

def _model_summary(
    loaded_tables: list[Table],
    staging_tables: list[Table],
    support_tables: list[Table],
    model: SemanticModel,
) -> str:
    """
    One-line summary placed at the top of Section 1.
    Uses generic "loaded / not loaded" language — no inferred type labels.
    """
    n_loaded   = len(loaded_tables)
    n_staging  = len(staging_tables)
    n_support  = len(support_tables)
    n_meas     = sum(len(t.measures) for t in model.tables)
    n_rels     = len(model.relationships)

    parts = [f"{n_loaded} loaded {'table' if n_loaded == 1 else 'tables'}"]
    if n_support:
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

    # Summary sentence
    lines += [_model_summary(loaded_tables, staging_tables, support_tables, model), ""]

    # Loaded tables
    if loaded_tables:
        lines += [
            "| Table | Source Type | Source |",
            "|---|---|---|",
        ]
        for t in loaded_tables:
            rs = get_table_source(t, resolved)
            if rs:
                src_type = _source_type_label(rs.source_type)
                label    = rs.manual_label or _source_detail(rs)
            else:
                src_type = "—"
                label    = "—"
            lines.append(f"| `{t.name}` | {src_type} | {label} |")
        lines.append("")
    else:
        lines += ["*No loaded tables found.*", ""]

    # Support tables block (calculated, field parameters, measures-only, calc groups)
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

    # Not-loaded tables block
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
                label    = rs.manual_label or _source_detail(rs)
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

    # Visible columns
    visible_cols = [c for c in table.columns if not c.is_hidden and not c.is_calculated]
    if visible_cols:
        lines += ["**Columns**", "", "| Column | Type |", "|---|---|"]
        for col in visible_cols:
            lines.append(f"| `{col.name}` | {_dtype(col.data_type)} |")
        lines.append("")

    # Hidden columns — listed compactly
    hidden_cols = [c for c in table.columns if c.is_hidden and not c.is_calculated]
    if hidden_cols:
        details = ", ".join(f"`{c.name}`" for c in hidden_cols)
        lines += [f"**Hidden Columns:** {details}  ", ""]

    # Calculated columns
    calc_cols = [c for c in table.columns if c.is_calculated]
    if calc_cols:
        lines += ["**Calculated Columns**", ""]
        for col in calc_cols:
            if include_dax and col.dax_expression:
                lines += [f"- **`{col.name}`**", "  ```dax", f"  {col.dax_expression[:200]}", "  ```"]
            else:
                lines.append(f"- `{col.name}`")
        lines.append("")

    # Calculation group items
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

    # Measures inline
    if table.measures:
        lines += ["**Measures**", "", "| Measure | Format | Description |", "|---|---|---|"]
        for m in table.measures:
            fmt  = f"`{m.format_string}`" if m.format_string else "—"
            desc = m.description or "—"
            lines.append(f"| `{m.name}` | {fmt} | {desc} |")
        if include_dax:
            lines += ["", "**Measure DAX**", ""]
            for m in table.measures:
                lines += [f"**`{m.name}`**", "```dax", m.dax_expression, "```", ""]

    return "\n".join(lines)


def _table_details_section(
    loaded_tables: list[Table],
    support_tables: list[Table],
    resolved: dict[str, ResolvedSource],
    include_dax: bool,
) -> str:
    lines = ["## 2. Table Details", ""]
    # Loaded tables first, then calc groups from support tables
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
                lines += [f"**`{m.name}`**", "```dax", m.dax_expression, "```", ""]

    lines += ["---", ""]
    return "\n".join(lines)


def _relationships_section(model: SemanticModel) -> str:
    lines = ["## 4. Relationships", ""]

    if not model.relationships:
        lines += ["*No relationships defined in this model.*", "", "---", ""]
        return "\n".join(lines)

    active   = [r for r in model.relationships if r.is_active]
    inactive = [r for r in model.relationships if not r.is_active]

    if active:
        lines += [
            "| From Table | From Column | To Table | To Column | Cardinality |",
            "|---|---|---|---|---|",
        ]
        for r in active:
            card = r.cardinality or "—"
            lines.append(
                f"| `{r.from_table}` | `{r.from_column}` | `{r.to_table}` | `{r.to_column}` | {card} |"
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
    """
    Returns a dict mapping parameter name -> list of expression names that
    directly reference it. Only catches structural references the parser
    already extracted into named fields (server, database, url, file_name, etc.).
    More complex patterns — conditional logic, Record.Field() calls, dynamic
    concatenation — are not detectable statically.
    """
    usage: dict[str, list[str]] = {p.name: [] for p in model.m_parameters}
    param_names = set(usage.keys())

    for expr in model.source_expressions:
        # Check every string field on the expression for [param:Name] markers
        for field_val in (
            expr.server, expr.database, expr.url,
            expr.file_name, expr.sharepoint_url, expr.dsn,
        ):
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

    lines += [
        "| Role | Table | Filter | Dynamic |",
        "|---|---|---|---|",
    ]
    for role in model.security_roles:
        if not role.table_filters:
            # Full access role — one row, no filter
            dynamic_label = f"Yes ({role.dynamic_function})" if role.is_dynamic else "No"
            lines.append(f"| `{role.name}` | — | — | {dynamic_label} |")
        else:
            for i, tf in enumerate(role.table_filters):
                role_cell   = f"`{role.name}`" if i == 0 else ""
                dynamic_label = f"Yes ({role.dynamic_function})" if role.is_dynamic else "No"
                dyn_cell    = dynamic_label if i == 0 else ""
                lines.append(f"| {role_cell} | `{tf.table}` | `{tf.dax_filter}` | {dyn_cell} |")

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
        used_by = usage_map.get(p.name, [])
        used_cell = ", ".join(f"`{e}`" for e in used_by) if used_by else "—"
        lines.append(f"| `{p.name}` | {p.param_type} | `{p.value}` | {used_cell} |")

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

    def names(lst: list) -> str:
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
        f"| Relationships | {len(model.relationships)} | — |",
        f"| Measures | {len(all_meas)} | — |",
        f"| Calculated Columns | {len(calc_cols)} | — |",
        "",
        "---",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def generate_readme(
    model: SemanticModel,
    resolved: dict[str, ResolvedSource],
    config: dict,
) -> str:
    """
    Generate a README.md string for a Power BI report.

    Args:
        model:    parsed SemanticModel from tmdl_parser
        resolved: resolved sources dict from source_resolver
        config:   dict with keys:
                    report_name       str   display name for the report
                    owner             str   report owner name
                    team              str   team name
                    refresh_schedule  str   human-readable schedule
                    include_dax       bool  whether to include DAX in output

    Returns:
        Markdown string ready to write to README.md
    """
    report_name = config.get("report_name", model.report_name)
    include_dax = config.get("include_dax", True)

    # Categorise tables
    support_types = {"calculated", "field_parameter", "measures_only", "calc_group"}
    loaded   = [t for t in model.tables if t.is_loaded and t.table_type not in support_types]
    support  = [t for t in model.tables if t.is_loaded and t.table_type in support_types]
    staging  = [t for t in model.tables if not t.is_loaded]

    sections = []

    # Header
    sections.append(f"# {report_name}\n")

    # Overview
    sections.append(_overview_section(config))

    # 1. Data Sources
    sections.append(_data_sources_section(loaded, staging, support, resolved, model))

    # 2. Table Details
    sections.append(_table_details_section(loaded, support, resolved, include_dax))

    # 3. Measures — always present
    sections.append(_measures_section(model.tables, include_dax))

    # 4. Relationships — always present
    sections.append(_relationships_section(model))

    # 5. Security Roles — always present
    sections.append(_security_roles_section(model))

    # 6. M Parameters — always present
    sections.append(_m_parameters_section(model))

    # Unresolved sources warning (only if needed)
    unresolved = _unresolved_section(resolved)
    if unresolved:
        sections.append(unresolved)

    # 7. Statistics
    sections.append(_statistics_section(model, loaded, support, staging))

    # Footer
    today = date.today().strftime("%d %B %Y")
    sections.append(f"*Generated by tmdl-lens · {today}*\n")

    return "\n".join(sections)
