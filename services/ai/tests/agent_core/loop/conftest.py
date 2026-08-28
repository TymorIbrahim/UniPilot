"""Fixtures for the loop package's tests.

`course_names` resolves a course code against the real catalog through the
shared `graph_registry`, so its tests need a real engine rather than a stub.

These two fixtures used to live in `tests/agent_core/tools/conftest.py` and were
re-exported from here. That tree was the V1 tool layer and has been retired, so
they are defined here now -- `course_names` is the only thing left that wants
them. `real_academic_engine` stays session-scoped: building the engine is the
expensive part and every test in this package shares one.
"""

from __future__ import annotations

from pathlib import Path

# Same directory depth as the tools conftest these came from, so parents[5] still
# lands on the repo root.
REPO_ROOT = Path(__file__).resolve().parents[5]
WIKI_DIR = REPO_ROOT / "services/data-engineering/data/catalog_valut/catalog_valut/wiki"
TECHNION_RAW_DIR = REPO_ROOT / "services/data-engineering/data/raw/technion"
CATALOG_JSON = TECHNION_RAW_DIR / "courses_2025_201.json"

import pytest

from app.retrieval.graph_engine.academic_graph_engine import AcademicGraphEngine
from app.retrieval.graph_engine.graph_registry import graph_registry


@pytest.fixture(scope="session")
def real_academic_engine() -> AcademicGraphEngine:
    """Real wiki + real semester-catalog engine, session-scoped so it's only
    built once across every test in this package. Skips when the real data
    isn't checked out locally.
    """
    if not WIKI_DIR.exists() or not CATALOG_JSON.exists():
        pytest.skip("Real wiki/catalog data not available locally")
    engine = AcademicGraphEngine()
    engine.load_from_paths(
        str(WIKI_DIR),
        str(TECHNION_RAW_DIR),
        semester_filename="courses_2025_201.json",
    )
    engine.build_graph()
    return engine


@pytest.fixture
def use_real_academic_engine(monkeypatch: pytest.MonkeyPatch, real_academic_engine: AcademicGraphEngine):
    """Point the shared `graph_registry` singleton at the real, already-built
    engine for the duration of one test -- decouples these tests from
    `Settings`/env vars entirely (no risk of polluting other tests' config).
    """
    monkeypatch.setattr(graph_registry, "is_configured", lambda *_a, **_k: True)
    monkeypatch.setattr(graph_registry, "get_engine", lambda *_a, **_k: real_academic_engine)
    return real_academic_engine
