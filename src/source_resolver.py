"""
source_resolver.py — Source resolution for tmdl-lens.

Takes the raw SourceExpression list from tmdl_parser and resolves:
  Tier 1  Direct source connectors — already fully classified by the parser.
  Tier 2  Derived expressions, parameter references, custom function calls.
          These are followed one level and resolved to their root source.
  Tier 3  Dynamic M (string concatenation, runtime variables).
          Flagged as unresolvable; caller may offer manual override.

Produces a flat dict  { expression_name: ResolvedSource }
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
    """
    The resolved data source for one expression / table.

    resolution_tier:
      1  Directly identified from M code
      2  Resolved by following a reference chain
      3  Could not be resolved (dynamic M / unresolvable)

    source_type mirrors SourceExpression.source_type after resolution.
    For derived expressions the resolved type reflects the root source.
    """
    expression_name: str
    source_type: str
    resolution_tier: int = 1

    # Human-readable label used in the README
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

    # Derivation chain
    derived_from: str = ""
    chain: list = field(default_factory=list)

    # Unresolved flag — set to True for Tier 3 or broken chains
    unresolved: bool = False
    unresolved_reason: str = ""

    # Optional manual override supplied by the user via the UI
    manual_label: str = ""


# ---------------------------------------------------------------------------
# Label builders
# ---------------------------------------------------------------------------

def _build_label(expr: SourceExpression, params: dict[str, str]) -> str:
    t = expr.source_type

    if t in ("dataflow_pbi", "dataflow_platform"):
        connector = "Power BI Dataflow" if t == "dataflow_pbi" else "Power Platform Dataflow"
        entity = expr.entity or "?"
        return f"{connector} → {entity}"

    if t == "sql":
        server = _resolve_param(expr.server, params)
        db     = _resolve_param(expr.database, params)
        if expr.schema and expr.table_or_view:
            return f"SQL · {server} · {db} · {expr.schema}.{expr.table_or_view}"
        return f"SQL · {server} · {db}"

    if t == "sql_native_query":
        server = _resolve_param(expr.server, params)
        db     = _resolve_param(expr.database, params)
        return f"SQL (native query) · {server} · {db}"

    if t == "odbc":
        dsn = expr.dsn or "?"
        tbl = f" → {expr.schema}.{expr.table_or_view}" if expr.table_or_view else ""
        return f"ODBC · {dsn}{tbl}"

    if t == "sharepoint_files":
        fn = f" / {expr.file_name}" if expr.file_name else ""
        return f"SharePoint Files · {expr.sharepoint_url}{fn}"

    if t == "sharepoint_tables":
        lst = f" → {expr.table_or_view}" if expr.table_or_view else ""
        return f"SharePoint List · {expr.sharepoint_url}{lst}"

    if t == "excel_sharepoint":
        fn    = expr.file_name or "?"
        sheet = f" / {expr.sheet_name}" if expr.sheet_name else ""
        return f"Excel (SharePoint) · {fn}{sheet}"

    if t == "excel_local":
        sheet = f" / {expr.sheet_name}" if expr.sheet_name else ""
        return f"Excel (local) · {expr.file_name}{sheet}"

    if t == "csv_local":
        return f"CSV (local) · {expr.file_name}"

    if t == "web_api":
        return f"Web API · {expr.url}"

    if t == "odata":
        tbl = f" → {expr.table_or_view}" if expr.table_or_view else ""
        return f"OData · {expr.url}{tbl}"

    if t == "hardcoded":
        return "Hardcoded table (inline M)"

    if t == "dynamic":
        return "Dynamic M (URL built at runtime)"

    if t in ("function_def", "scalar_helper"):
        return f"Helper ({t})"

    return expr.name


def _resolve_param(value: str, params: dict[str, str]) -> str:
    """Substitutes [param:ParamName] placeholders with their actual values."""
    if value.startswith("[param:") and value.endswith("]"):
        param_name = value[7:-1]
        return params.get(param_name, value)
    return value


# ---------------------------------------------------------------------------
# Core resolver
# ---------------------------------------------------------------------------

def resolve_sources(
    source_expressions: list[SourceExpression],
    m_parameters: list[MParameter],
    manual_overrides: Optional[dict[str, str]] = None,
) -> dict[str, ResolvedSource]:
    """
    Resolves all source expressions and returns a dict keyed by expression name.

    Args:
        source_expressions: list from tmdl_parser.parse_semantic_model
        m_parameters:       list from tmdl_parser.parse_semantic_model
        manual_overrides:   dict { expression_name: label } supplied by the user
                            for Tier 3 / unresolvable sources

    Returns:
        dict { expression_name: ResolvedSource }
    """
    manual_overrides = manual_overrides or {}
    params: dict[str, str] = {p.name: p.value for p in m_parameters}
    expr_map: dict[str, SourceExpression] = {e.name: e for e in source_expressions}
    resolved: dict[str, ResolvedSource] = {}

    # ── Pass 1: resolve all Tier 1 expressions directly ──────────────────────
    for expr in source_expressions:
        if expr.source_type in (
            "dataflow_pbi", "dataflow_platform",
            "sql", "sql_native_query",
            "odbc",
            "sharepoint_files", "sharepoint_tables",
            "excel_sharepoint", "excel_local",
            "csv_local",
            "web_api", "odata",
            "hardcoded",
            "function_def", "scalar_helper",
        ):
            rs = _from_expr(expr, params, tier=1)
            # Apply manual override label if provided
            if expr.name in manual_overrides:
                rs.manual_label = manual_overrides[expr.name]
                rs.label        = manual_overrides[expr.name]
            resolved[expr.name] = rs

    # ── Pass 2: resolve derived / custom_function (Tier 2) ───────────────────
    # May need multiple passes if chains are more than one level deep.
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
                    rs = ResolvedSource(
                        expression_name=expr.name,
                        source_type=parent.source_type,
                        resolution_tier=2,
                        label=parent.label,
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
                        derived_from=parent_name,
                        chain=parent.chain + [parent_name],
                    )
                    resolved[expr.name] = rs
                elif parent_name not in expr_map:
                    resolved[expr.name] = _unresolved(
                        expr.name, f"references '{parent_name}' which does not exist"
                    )

            elif expr.source_type == "custom_function":
                fn_name = expr.function_name
                if fn_name in resolved:
                    # Custom function is already resolved (e.g. wraps a dataflow connector)
                    parent = resolved[fn_name]
                    rs = ResolvedSource(
                        expression_name=expr.name,
                        source_type=parent.source_type,
                        resolution_tier=2,
                        label=parent.label,
                        workspace_id=parent.workspace_id,
                        dataflow_id=parent.dataflow_id,
                        entity=expr.function_args.strip('"').split(",")[-1].strip().strip('"') or parent.entity,
                        server=parent.server,
                        database=parent.database,
                        schema=parent.schema,
                        table_or_view=parent.table_or_view,
                        derived_from=fn_name,
                        chain=[fn_name],
                    )
                    # Rebuild label with the entity extracted from function args
                    if rs.source_type in ("dataflow_pbi", "dataflow_platform") and rs.entity:
                        connector = "Power BI Dataflow" if rs.source_type == "dataflow_pbi" else "Power Platform Dataflow"
                        rs.label = f"{connector} → {rs.entity}"
                    resolved[expr.name] = rs
                elif fn_name in expr_map:
                    pass  # function definition not yet resolved — retry next pass
                else:
                    resolved[expr.name] = _unresolved(
                        expr.name, f"calls function '{fn_name}' which is not defined in this model"
                    )

    # ── Pass 3: anything still unresolved is Tier 3 ──────────────────────────
    for expr in source_expressions:
        if expr.name in resolved:
            continue
        if expr.source_type == "dynamic":
            rs = _unresolved(expr.name, "Dynamic M - URL or query is built at runtime and cannot be statically resolved")
            rs.source_type = "dynamic"
            rs.label       = "Dynamic M (runtime URL)"
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

    return resolved


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
    )
    rs.label = _build_label(expr, params)
    return rs


def _unresolved(name: str, reason: str) -> ResolvedSource:
    return ResolvedSource(
        expression_name=name,
        source_type="unresolved",
        resolution_tier=3,
        label=f"⚠ Unresolved — {reason}",
        unresolved=True,
        unresolved_reason=reason,
    )


# ---------------------------------------------------------------------------
# Convenience: get resolved source for a table
# ---------------------------------------------------------------------------

def get_table_source(
    table,                          # tmdl_parser.Table
    resolved: dict[str, ResolvedSource],
) -> Optional[ResolvedSource]:
    """
    Returns the ResolvedSource for a given Table, or None if not applicable
    (e.g. calculated tables, measures-only tables).
    """
    if table.source_ref:
        return resolved.get(table.source_ref)
    return None


def list_unresolved(resolved: dict[str, ResolvedSource]) -> list[ResolvedSource]:
    """Returns all ResolvedSource entries that are still unresolved."""
    return [rs for rs in resolved.values() if rs.unresolved]
