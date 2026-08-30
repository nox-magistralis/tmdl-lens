"""
conftest.py — shared pytest fixtures for tmdl-lens tests.

All tests run against the bundled sample report in sample/.
"""

import os
import sys

import pytest

# Make the repo root importable (tmdl_lens/ is not installed as a package).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tmdl_lens.source_resolver import resolve_sources  # noqa: E402
from tmdl_lens.tmdl_parser import parse_semantic_model  # noqa: E402

# Windows consoles often default to a legacy codec (e.g. cp1250). Force
# UTF-8 for test output so unicode markers never crash the run.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE_MODEL = os.path.join(
    REPO_ROOT, "sample", "tmdl-lens-test-report.SemanticModel"
)


@pytest.fixture(scope="session")
def sample_model():
    """Parsed SemanticModel for the bundled sample report."""
    return parse_semantic_model(SAMPLE_MODEL, "tmdl-lens Test Report")


@pytest.fixture(scope="session")
def sample_resolved(sample_model):
    """Resolved source dict for the bundled sample report."""
    return resolve_sources(
        sample_model.source_expressions, sample_model.m_parameters
    )


@pytest.fixture(scope="session")
def gen_config():
    """Generator config with non-empty documentation metadata."""
    return {
        "report_name":      "tmdl-lens Test Report",
        "owner":            "Report Owner",
        "team":             "BI Team",
        "refresh_schedule": "Daily at 06:00 UTC",
        "include_dax":      True,
    }
