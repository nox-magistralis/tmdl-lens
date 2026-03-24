"""
test_parse.py — Validates tmdl_parser + source_resolver against the sample report.
Run from the repo root:  python tests/test_parse.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.tmdl_parser import parse_semantic_model
from src.source_resolver import resolve_sources, list_unresolved, get_table_source

SAMPLE_MODEL = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "sample",
    "tmdl-lens-test-report.SemanticModel",
)


def separator(title: str):
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


def run():
    # ── 1. Parse ─────────────────────────────────────────────────────────────
    separator("1. Parsing semantic model")
    model = parse_semantic_model(SAMPLE_MODEL, "tmdl-lens Test Report")
    print(f"  Report         : {model.report_name}")
    print(f"  Tables         : {len(model.tables)}")
    print(f"  Relationships  : {len(model.relationships)}")
    print(f"  Expressions    : {len(model.source_expressions)}")
    print(f"  M Parameters   : {len(model.m_parameters)}")

    # ── 2. Tables ─────────────────────────────────────────────────────────────
    separator("2. Tables")
    for t in model.tables:
        loaded_flag = "" if t.is_loaded else " [NOT LOADED]"
        hidden_flag = " [HIDDEN]" if t.is_hidden else ""
        print(f"  {t.name:<35} type={t.table_type:<16} partition={t.partition_type or '—':<12} ref='{t.source_ref}'{loaded_flag}{hidden_flag}")

    # ── 3. M Parameters ───────────────────────────────────────────────────────
    separator("3. M Parameters")
    for p in model.m_parameters:
        print(f"  {p.name:<20} type={p.param_type:<10} value={p.value}")

    # ── 4. Raw expressions (before resolution) ────────────────────────────────
    separator("4. Source expressions (raw)")
    for e in model.source_expressions:
        print(f"  {e.name:<40} source_type={e.source_type}")

    # ── 5. Resolve ────────────────────────────────────────────────────────────
    separator("5. Resolving sources")
    resolved = resolve_sources(model.source_expressions, model.m_parameters)
    for name, rs in resolved.items():
        tier   = f"T{rs.resolution_tier}"
        unresx = " ⚠ UNRESOLVED" if rs.unresolved else ""
        print(f"  [{tier}] {name:<40} → {rs.label}{unresx}")

    # ── 6. Unresolved list ────────────────────────────────────────────────────
    unresolved = list_unresolved(resolved)
    separator(f"6. Unresolved sources ({len(unresolved)})")
    if unresolved:
        for rs in unresolved:
            print(f"  ⚠  {rs.expression_name}")
            print(f"     Reason: {rs.unresolved_reason}")
    else:
        print("  All sources resolved.")

    # ── 7. Table → source mapping ─────────────────────────────────────────────
    separator("7. Table → resolved source")
    for t in model.tables:
        rs = get_table_source(t, resolved)
        if rs:
            tier = f"T{rs.resolution_tier}"
            flag = " ⚠" if rs.unresolved else ""
            print(f"  {t.name:<35} [{tier}] {rs.label}{flag}")
        else:
            print(f"  {t.name:<35} — (no M source: {t.table_type})")

    # ── 8. Relationships ──────────────────────────────────────────────────────
    separator("8. Relationships")
    if model.relationships:
        for r in model.relationships:
            active = "" if r.is_active else " [inactive]"
            print(f"  {r.from_table}.{r.from_column}  →  {r.to_table}.{r.to_column}{active}")
    else:
        print("  (none found — relationships.tmdl may be empty or absent)")

    # ── 9. Measures ───────────────────────────────────────────────────────────
    separator("9. Measures")
    for t in model.tables:
        for m in t.measures:
            print(f"  [{t.name}]  {m.name:<30}  fmt={m.format_string or '—'}")

    # ── 10. Summary ───────────────────────────────────────────────────────────
    separator("10. Summary")
    tier_counts = {1: 0, 2: 0, 3: 0}
    for rs in resolved.values():
        tier_counts[rs.resolution_tier] = tier_counts.get(rs.resolution_tier, 0) + 1

    print(f"  Tier 1 (direct)   : {tier_counts[1]}")
    print(f"  Tier 2 (derived)  : {tier_counts[2]}")
    print(f"  Tier 3 (unresolved): {tier_counts[3]}")
    print(f"  Total expressions : {len(resolved)}")

    if unresolved:
        print(f"\n  ⚠  {len(unresolved)} source(s) need manual labelling.")
    else:
        print("\n  ✓  Parser + resolver working correctly.")


if __name__ == "__main__":
    run()
