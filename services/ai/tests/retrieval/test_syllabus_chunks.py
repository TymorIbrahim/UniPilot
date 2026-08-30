"""Catalog syllabi as local BM25 chunks for courses the wiki does not cover.

User: "yes" to BM25 syllabus snippets for offered courses with no wiki page.
Callers: AcademicGraphEngine.search_wiki, WikiRetriever.search / page.
Not Pinecone: wiki_index_sync still indexes markdown only.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.retrieval.graph_engine.academic_graph_engine import AcademicGraphEngine
from app.retrieval.graph_engine.syllabus_chunks import syllabus_chunks_for_identity

WIKI_COVERED = "00940111"
NO_WIKI = "00940222"
EMPTY_SYLLABUS = "00940333"


def _entry(code: str, *, name: str, syllabus: str) -> dict:
    return {
        "general": {
            "מספר מקצוע": code,
            "שם מקצוע": name,
            "סילבוס": syllabus,
            "נקודות": "3.0",
            "פקולטה": "Computer Science",
        },
        "schedule": [],
    }


def test_builder_skips_wiki_covered_and_empty_syllabi():
    identity = {
        WIKI_COVERED: _entry(
            WIKI_COVERED,
            name="Covered Course",
            syllabus="A long enough wiki-covered syllabus about compilers.",
        ),
        NO_WIKI: _entry(
            NO_WIKI,
            name="Hidden Course",
            syllabus="Unique phrase about Kalman filtering for aerospace.",
        ),
        EMPTY_SYLLABUS: _entry(EMPTY_SYLLABUS, name="Bare", syllabus=""),
    }
    chunks = syllabus_chunks_for_identity(identity, wiki_course_codes={WIKI_COVERED})
    codes = {chunk.primary_course_number for chunk in chunks}
    assert codes == {NO_WIKI}
    chunk = chunks[0]
    assert "Kalman filtering" in chunk.content
    assert chunk.source_file.startswith("syllabus/")


def test_search_wiki_returns_identity_syllabus_when_no_wiki_page(tmp_path: Path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "index.md").write_text(
        "---\ntitle: Index\n---\n\nCatalog index page with filler text.\n",
        encoding="utf-8",
    )
    (tmp_path / "courses_2025_201.json").write_text(
        json.dumps(
            [
                _entry(
                    NO_WIKI,
                    name="Hidden Course",
                    syllabus="Unique phrase about Kalman filtering for aerospace.",
                ),
                _entry(
                    WIKI_COVERED,
                    name="Covered Course",
                    syllabus="Compilers syllabus that should not be chunked.",
                ),
            ]
        ),
        encoding="utf-8",
    )
    (wiki / "courses").mkdir()
    (wiki / "courses" / f"{WIKI_COVERED}.md").write_text(
        f"---\ntitle: Covered\ncourse_code: {WIKI_COVERED}\n---\n\n"
        "Wiki unique phrase about LR parsing tables.\n",
        encoding="utf-8",
    )

    engine = AcademicGraphEngine()
    engine.load_from_paths(str(wiki), str(tmp_path), semester_filename="courses_2025_201.json")
    engine.build_graph()

    hits = engine.search_wiki("Kalman filtering")
    slugs = [hit["slug"] for hit in hits]
    assert NO_WIKI in slugs
    hit = next(item for item in hits if item["slug"] == NO_WIKI)
    assert hit["kind"] == "syllabus"
    assert "Kalman filtering" in hit["content"]

    codes = {chunk.primary_course_number for chunk in engine.syllabus_chunks}
    assert NO_WIKI in codes
    assert WIKI_COVERED not in codes

    wiki_hits = engine.search_wiki("LR parsing tables")
    assert any(hit["slug"] == WIKI_COVERED for hit in wiki_hits)


def test_wiki_retriever_page_falls_back_to_syllabus_chunk(tmp_path: Path):
    from app.agent_core.facts.wiring import WikiRetriever

    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "index.md").write_text(
        "---\ntitle: Index\n---\n\nCatalog index page with filler text.\n",
        encoding="utf-8",
    )
    (tmp_path / "courses_2025_201.json").write_text(
        json.dumps(
            [
                _entry(
                    NO_WIKI,
                    name="Hidden Course",
                    syllabus="Unique phrase about Kalman filtering for aerospace.",
                )
            ]
        ),
        encoding="utf-8",
    )
    engine = AcademicGraphEngine()
    engine.load_from_paths(str(wiki), str(tmp_path), semester_filename="courses_2025_201.json")
    engine.build_graph()

    retriever = WikiRetriever(engine)
    page = retriever.page(NO_WIKI)
    assert page is not None
    assert "Kalman filtering" in page
    assert retriever.page("missing-slug") is None
