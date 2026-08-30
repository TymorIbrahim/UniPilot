"""Local BM25 documents from catalog syllabi when the wiki has no course page.

AcademicGraphEngine.search_wiki unions these with wiki chunks. They are
never passed to wiki_index_sync / Pinecone.
"""

from __future__ import annotations

from typing import Any, Mapping

from app.retrieval.obsidian_wiki_indexer import (
    WikiChunk,
    detect_language,
    is_substantive,
)


def syllabus_chunks_for_identity(
    identity_catalog: Mapping[str, Mapping[str, Any]],
    wiki_course_codes: set[str],
) -> tuple[WikiChunk, ...]:
    """One chunk per identity course that has syllabus text and no wiki page."""
    chunks: list[WikiChunk] = []
    covered = {code for code in wiki_course_codes if code}
    for code, entry in identity_catalog.items():
        if not code or code in covered or "/" in code or ".." in code:
            continue
        general = entry.get("general") if isinstance(entry, Mapping) else None
        if not isinstance(general, Mapping):
            continue
        syllabus = str(general.get("סילבוס", "") or "").strip()
        name = str(general.get("שם מקצוע", "") or "").strip()
        if not is_substantive(syllabus):
            continue
        faculty = str(general.get("פקולטה", "") or "").strip() or None
        credits = str(general.get("נקודות", "") or "").strip() or None
        title = name or code
        content = f"{code} {title}\n{syllabus}".strip()
        chunks.append(
            WikiChunk(
                source_file=f"syllabus/{code}.md",
                page_title=title,
                section_title="Syllabus",
                heading_path=(title, "Syllabus"),
                content=content,
                faculty=faculty,
                course_numbers_mentioned=(code,),
                primary_course_number=code,
                language=detect_language(content),
                aliases=(name,) if name else (),
                credits=credits,
            )
        )
    return tuple(chunks)
