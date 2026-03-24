"""
test_readme.py — Generates a README.md from the sample report and writes it
to sample/tmdl-lens-test-report.SemanticModel/../README.md for inspection.

Run from the repo root:  python tests/test_readme.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.tmdl_parser import parse_semantic_model
from src.source_resolver import resolve_sources
from src.readme_generator import generate_readme

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SAMPLE_MODEL = os.path.join(
    REPO_ROOT, "sample", "tmdl-lens-test-report.SemanticModel"
)

OUTPUT_PATH = os.path.join(
    REPO_ROOT, "sample", "README.md"
)

CONFIG = {
    "report_name":      "tmdl-lens Test Report",
    "owner":            "Report Owner",
    "team":             "BI Team",
    "refresh_schedule": "Daily at 06:00 UTC",
    "include_dax":      True,
}


def run():
    print("Parsing semantic model...")
    model = parse_semantic_model(SAMPLE_MODEL, CONFIG["report_name"])
    print(f"  Tables      : {len(model.tables)}")
    print(f"  Expressions : {len(model.source_expressions)}")
    print(f"  Parameters  : {len(model.m_parameters)}")

    print("\nResolving sources...")
    resolved = resolve_sources(model.source_expressions, model.m_parameters)
    unresolved = [rs for rs in resolved.values() if rs.unresolved]
    print(f"  Resolved    : {len(resolved) - len(unresolved)}")
    print(f"  Unresolved  : {len(unresolved)}")

    print("\nGenerating README...")
    readme = generate_readme(model, resolved, CONFIG)

    print(f"\nWriting to: {OUTPUT_PATH}")
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(readme)

    print(f"  Done — {len(readme.splitlines())} lines written.")
    print(f"\nOpen {OUTPUT_PATH} to inspect the output.")


if __name__ == "__main__":
    run()
