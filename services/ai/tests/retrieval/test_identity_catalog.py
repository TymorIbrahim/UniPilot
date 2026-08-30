"""Winter+spring identity catalog vs semester-scoped offerings.

The graph used to build course nodes from ONE offering JSON. Winter-only
courses then had no prereqs, syllabus, or name unless a wiki page existed.
Identity is the union of the live winter+spring files; the active semester
still owns schedule and "offered this term".
"""

from __future__ import annotations

import json
from pathlib import Path

from app.retrieval.graph_engine.academic_graph_engine import AcademicGraphEngine

WINTER_ONLY = "00940111"
SPRING_ONLY = "00940222"
BOTH = "00940333"
SUMMER_ONLY = "00940444"


def _entry(code: str, *, name: str, syllabus: str, prereq: str, schedule: list[dict]) -> dict:
    return {
        "general": {
            "מספר מקצוע": code,
            "שם מקצוע": name,
            "סילבוס": syllabus,
            "מקצועות קדם": prereq,
            "נקודות": "3.5",
            "פקולטה": "Data and Decision Sciences",
        },
        "schedule": schedule,
    }


def _write(path: Path, entries: list[dict]) -> None:
    path.write_text(json.dumps(entries), encoding="utf-8")


def _engine(raw: Path, active: str) -> AcademicGraphEngine:
    wiki = raw / "wiki"
    wiki.mkdir()
    (wiki / "index.md").write_text("---\ntitle: Index\n---\n\nCatalog index page.\n", encoding="utf-8")
    engine = AcademicGraphEngine()
    engine.load_from_paths(str(wiki), str(raw), semester_filename=active)
    engine.build_graph()
    return engine


def test_winter_only_course_is_in_the_graph_when_spring_is_active(tmp_path: Path):
    _write(
        tmp_path / "courses_2025_200.json",
        [
            _entry(
                WINTER_ONLY,
                name="Winter Only",
                syllabus="Winter syllabus about linear models.",
                prereq="00940001",
                schedule=[{"יום": "ראשון", "שעה": "10:00 - 12:00"}],
            ),
            _entry(
                BOTH,
                name="Both Terms Winter",
                syllabus="Shared course winter notes.",
                prereq="",
                schedule=[{"יום": "שני", "שעה": "08:00 - 10:00"}],
            ),
        ],
    )
    _write(
        tmp_path / "courses_2025_201.json",
        [
            _entry(
                SPRING_ONLY,
                name="Spring Only",
                syllabus="Spring syllabus about databases.",
                prereq="",
                schedule=[{"יום": "שלישי", "שעה": "14:00 - 16:00"}],
            ),
            _entry(
                BOTH,
                name="Both Terms Spring",
                syllabus="Shared course spring notes.",
                prereq="",
                schedule=[{"יום": "רביעי", "שעה": "12:00 - 14:00"}],
            ),
        ],
    )
    engine = _engine(tmp_path, "courses_2025_201.json")

    assert WINTER_ONLY in engine.identity_catalog
    assert SPRING_ONLY in engine.identity_catalog
    assert BOTH in engine.identity_catalog
    # Offerings stay spring-scoped so "is it this term" does not mix hours.
    assert WINTER_ONLY not in engine.course_catalog
    assert SPRING_ONLY in engine.course_catalog
    assert len(engine.course_catalog) == 2

    node = engine.graph.nodes[WINTER_ONLY]
    assert node["name"] == "Winter Only"
    assert "linear models" in node["syllabus"]
    assert node["schedule"] == []
    eligible, missing = engine.evaluate_eligibility(WINTER_ONLY, [])
    assert eligible is False
    assert "00940001" in missing

    spring_node = engine.graph.nodes[SPRING_ONLY]
    assert spring_node["schedule"]
    both = engine.graph.nodes[BOTH]
    assert both["name"] == "Both Terms Spring"
    assert both["schedule"][0]["יום"] == "רביעי"

    winter_sched = engine.retrieve_context("schedule", course_id=WINTER_ONLY)
    assert "not offered this term" in winter_sched.lower()
    spring_sched = engine.retrieve_context("schedule", course_id=SPRING_ONLY)
    assert "not offered this term" not in spring_sched.lower()
    info = engine.retrieve_context("course_info", course_id=WINTER_ONLY)
    assert "offered_this_term: no" in info

    stats = engine.graph_stats()
    assert stats["courses_in_catalog"] == 2
    assert stats["identity_courses"] == 3


def test_switching_to_winter_fills_schedule_without_dropping_spring_identity(tmp_path: Path):
    _write(
        tmp_path / "courses_2025_200.json",
        [
            _entry(
                WINTER_ONLY,
                name="Winter Only",
                syllabus="Winter syllabus about linear models.",
                prereq="",
                schedule=[{"יום": "ראשון", "שעה": "10:00 - 12:00"}],
            ),
        ],
    )
    _write(
        tmp_path / "courses_2025_201.json",
        [
            _entry(
                SPRING_ONLY,
                name="Spring Only",
                syllabus="Spring syllabus about databases.",
                prereq="",
                schedule=[{"יום": "שלישי", "שעה": "14:00 - 16:00"}],
            ),
        ],
    )
    engine = _engine(tmp_path, "courses_2025_201.json")
    engine.set_active_semester("courses_2025_200.json", str(tmp_path))
    engine.build_graph()

    assert SPRING_ONLY in engine.identity_catalog
    assert engine.graph.nodes[WINTER_ONLY]["schedule"]
    assert engine.graph.nodes[SPRING_ONLY]["schedule"] == []
    assert len(engine.course_catalog) == 1


def test_summer_only_offering_stays_in_the_graph(tmp_path: Path):
    """Identity excludes summer, but this-term summer courses still get nodes."""
    _write(
        tmp_path / "courses_2025_200.json",
        [
            _entry(
                WINTER_ONLY,
                name="Winter Only",
                syllabus="Winter syllabus.",
                prereq="",
                schedule=[{"יום": "ראשון", "שעה": "10:00 - 12:00"}],
            ),
        ],
    )
    _write(
        tmp_path / "courses_2025_201.json",
        [
            _entry(
                SPRING_ONLY,
                name="Spring Only",
                syllabus="Spring syllabus.",
                prereq="",
                schedule=[{"יום": "שלישי", "שעה": "14:00 - 16:00"}],
            ),
        ],
    )
    _write(
        tmp_path / "courses_2025_202.json",
        [
            _entry(
                SUMMER_ONLY,
                name="Summer Only",
                syllabus="Summer syllabus.",
                prereq="",
                schedule=[{"יום": "חמישי", "שעה": "09:00 - 11:00"}],
            ),
        ],
    )
    engine = _engine(tmp_path, "courses_2025_202.json")

    assert SUMMER_ONLY in engine.course_catalog
    assert SUMMER_ONLY not in engine.identity_catalog
    assert WINTER_ONLY in engine.identity_catalog
    assert SUMMER_ONLY in engine.graph.nodes
    assert engine.graph.nodes[SUMMER_ONLY]["schedule"]
    assert engine.graph.nodes[WINTER_ONLY]["schedule"] == []
    assert engine.retrieve_context("schedule", course_id=SUMMER_ONLY).count("09:00")
    assert "not offered this term" in engine.retrieve_context(
        "schedule", course_id=WINTER_ONLY
    ).lower()



def test_unreadable_identity_file_does_not_crash_graph_load(tmp_path: Path):
    """A truncated winter JSON must not prevent spring identity from loading."""
    (tmp_path / "courses_2025_200.json").write_text("{not-json", encoding="utf-8")
    _write(
        tmp_path / "courses_2025_201.json",
        [
            _entry(
                SPRING_ONLY,
                name="Spring Only",
                syllabus="Spring syllabus about databases.",
                prereq="",
                schedule=[{"יום": "שלישי", "שעה": "14:00 - 16:00"}],
            ),
        ],
    )
    engine = _engine(tmp_path, "courses_2025_201.json")
    assert SPRING_ONLY in engine.identity_catalog
    assert SPRING_ONLY in engine.graph.nodes
    assert "courses_2025_201.json" in engine.identity_semesters
    assert "courses_2025_200.json" not in engine.identity_semesters
