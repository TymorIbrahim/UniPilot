"""Additional Phase D coverage for faculty export and context helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.catalog.faculty_catalog_context import (
    FacultyCatalogContext,
    faculty_catalog_context_from_document,
    faculty_catalog_context_from_staging_program,
    faculty_id_from_document,
    production_advisory_requirement_key,
    production_requirement_key,
)
from app.importers.dds_catalog_staging_importer import (
    CatalogStagingImportError,
    validate_catalog_structure,
)
from app.paths import faculty_catalog_export_dir
from app.quality.dds_staging_quality import build_dds_staging_quality_report
from app.vault.export_faculty_vault_catalog import (
    _bucket_requirement_type,
    _canonical_bucket_slug,
    _dedupe_requirement_groups,
    _missing_standard_technion_bucket_slugs,
    _slugify_bucket_label,
    build_generic_program,
    export_faculty_vault_catalog,
    should_export_degree_program,
    parse_credit_buckets_from_page,
)
from app.vault.loader import WikiPage


def test_faculty_id_from_document_fallback_paths() -> None:
    assert faculty_id_from_document({}) == "dds"
    assert faculty_id_from_document({"parserReport": {"faculty": "math"}}) == "math"
    assert faculty_id_from_document(
        {"programs": [{"metadata": {"facultyId": "faculty-physics"}}]}
    ) == "physics"
    assert faculty_id_from_document(
        {"programs": [{"metadata": {"faculty": "chemistry"}}]}
    ) == "chemistry"


def test_faculty_context_from_staging_program_variants() -> None:
    assert faculty_catalog_context_from_staging_program({}) is None
    context = faculty_catalog_context_from_staging_program(
        {"sourceName": "technion-math-catalog", "programCode": "010001-1-000"}
    )
    assert context is not None
    assert context.faculty_id == "math"
    context2 = faculty_catalog_context_from_staging_program(
        {
            "metadata": {"facultyId": "faculty-biology"},
            "sourceName": "technion-biology-catalog",
            "programCode": "010002-1-000",
            "sourceMetadata": {"exportMode": "specialized"},
        }
    )
    assert context2 is not None
    assert context2.faculty_id == "biology"
    assert context2.export_mode == "specialized"


def test_faculty_context_production_key_prefix() -> None:
    context = faculty_catalog_context_from_document(
        {"source": {"facultyId": "dds"}, "programs": []}
    )
    assert context.production_key_prefix == "technion-dds"
    assert production_requirement_key("dds", "G1", "2025-2026") == "technion-dds:requirement:G1:2025-2026"
    assert (
        production_advisory_requirement_key("dds", "G1", "2025-2026")
        == "technion-dds:advisory-rule:req:G1:2025-2026"
    )


def test_faculty_catalog_export_dir_non_dds() -> None:
    path = faculty_catalog_export_dir("computer-science")
    assert path.name == "computer-science"


def test_validate_catalog_structure_generic_faculty_paths() -> None:
    program = MagicMock()
    program.programCode = "023023-1-000"
    program.totalCredits = 0
    program.requirementGroups = []
    doc = MagicMock()
    doc.programs = [program]
    doc.model_dump.return_value = {
        "source": {
            "facultyId": "computer-science",
            "expectedProgramCodes": ["023023-1-000"],
        },
        "programs": [{"programCode": "023023-1-000"}],
    }
    context = FacultyCatalogContext(
        faculty_id="computer-science",
        source_name="technion-computer-science-catalog",
        source_type="computer-science_catalog_curated_reviewed",
        expected_program_codes=("023023-1-000",),
        export_mode="specialized",
    )
    with pytest.raises(CatalogStagingImportError, match="totalCredits must be a positive"):
        validate_catalog_structure(doc, context=context)

    empty_doc = MagicMock()
    empty_doc.programs = []
    empty_doc.model_dump.return_value = {"source": {"facultyId": "computer-science"}, "programs": []}
    with pytest.raises(CatalogStagingImportError, match="at least one program"):
        validate_catalog_structure(empty_doc, context=context)


def test_generic_bucket_helpers() -> None:
    assert _slugify_bucket_label("מקצועות חובה") == "required-courses"
    assert _slugify_bucket_label("מקצועות העשרה") == "enrichment"
    assert _slugify_bucket_label("Free electives") == "free-elective"
    assert _canonical_bucket_slug("free-electives") == "free-elective"
    assert _missing_standard_technion_bucket_slugs({"enrichment", "physical-education", "free-electives"}) == set()
    assert _bucket_requirement_type("Physical education") == "enrichment"
    assert _bucket_requirement_type("Faculty electives") == "elective"
    assert _bucket_requirement_type("Core required") == "core"


def test_dedupe_requirement_groups_merges_course_refs_and_skips_blank_ids() -> None:
    merged = _dedupe_requirement_groups(
        [
            {"groupId": "", "courseReferences": [{"courseNumber": "01040001"}]},
            {
                "groupId": "010040-1-000:semester-1-matrix",
                "courseReferences": [{"courseNumber": "01040001"}],
            },
            {
                "groupId": "010040-1-000:semester-1-matrix",
                "courseReferences": [{"courseNumber": "01040002"}],
            },
        ]
    )
    assert len(merged) == 1
    assert {ref["courseNumber"] for ref in merged[0]["courseReferences"]} == {
        "01040001",
        "01040002",
    }


def test_slugify_bucket_label_falls_back_to_hash_for_unknown_hebrew() -> None:
    slug = _slugify_bucket_label("קטגוריה לא מוכרת")
    assert slug.startswith("bucket-")


def test_build_generic_program_without_program_code() -> None:
    page = WikiPage(
        slug="track-test",
        path=Path("/tmp/track-test.md"),
        frontmatter={},
        body="",
        english_body="**Track code:** TBD\n",
    )
    assert build_generic_program(page, faculty_id="math", pages={}) is None


def test_parse_credit_buckets_skips_invalid_rows() -> None:
    page = WikiPage(
        slug="track-test",
        path=Path("/tmp/track-test.md"),
        frontmatter={},
        body="",
        english_body=(
            "| Category | Credits |\n"
            "|---|---|\n"
            "| **Total** | 155.0 |\n"
            "| Required | not-a-number |\n"
            "| Electives | 12.0 |\n"
        ),
    )
    buckets = parse_credit_buckets_from_page(page)
    assert len(buckets) == 1


def test_export_faculty_vault_catalog_raises_when_no_programs(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.vault.export_faculty_vault_catalog.discover_faculty_track_slugs",
        lambda pages, faculty_id: ["track-empty"],
    )
    monkeypatch.setattr(
        "app.vault.export_faculty_vault_catalog.build_generic_program",
        lambda page, faculty_id, pages: None,
    )
    with pytest.raises(ValueError, match="No exportable BSc track programs"):
        export_faculty_vault_catalog(faculty_id="math")


def test_build_quality_report_for_generic_faculty(mongo_database) -> None:
    from app.config import get_settings

    settings = get_settings()
    mongo_database[settings.staging_degree_programs_collection].insert_one(
        {
            "sourceName": "technion-math-catalog",
            "programCode": "010001-1-000",
            "totalCredits": 155.0,
            "signoffReview": {"reviewStatus": "ok"},
        }
    )
    mongo_database[settings.staging_degree_requirements_collection].insert_one(
        {
            "sourceName": "technion-math-catalog",
            "requirementGroup": {"groupId": "010001-1-000:core", "courseReferences": []},
        }
    )
    report = build_dds_staging_quality_report(mongo_database, settings=settings, faculty_id="math")
    assert report.counts.get("programs") == 1


def test_normalize_faculty_id_empty() -> None:
    from app.catalog.faculty_catalog_context import _normalize_faculty_id

    assert _normalize_faculty_id(None) == "unknown"
    assert _normalize_faculty_id("") == "unknown"


def test_discover_faculty_tracks_from_tags() -> None:
    from app.vault.export_faculty_vault_catalog import discover_faculty_track_slugs
    from app.vault.loader import WikiPage

    pages = {
        "track-tagged-only": WikiPage(
            slug="track-tagged-only",
            path=Path("/tmp/tagged.md"),
            frontmatter={"tags": ["faculty-math"]},
            body="",
            english_body="",
        )
    }
    assert discover_faculty_track_slugs(pages, "math") == ["track-tagged-only"]


def test_extract_program_code_multiline_pattern() -> None:
    from app.vault.export_faculty_vault_catalog import extract_program_code
    from app.vault.loader import WikiPage

    page = WikiPage(
        slug="track-test",
        path=Path("/tmp/track-test.md"),
        frontmatter={},
        body="",
        english_body="**Program code:** 010001-1-000\n",
    )
    assert extract_program_code(page) == "010001-1-000"


def test_parse_credit_buckets_skips_short_rows() -> None:
    from app.vault.export_faculty_vault_catalog import parse_credit_buckets_from_page
    from app.vault.loader import WikiPage

    page = WikiPage(
        slug="track-test",
        path=Path("/tmp/track-test.md"),
        frontmatter={},
        body="",
        english_body="| Category | Credits |\n|---|---|\n| Required |\n",
    )
    assert parse_credit_buckets_from_page(page) == []


def test_promotion_gate_filters_path_options_and_faculties_by_scope(mongo_database) -> None:
    from app.config import get_settings
    from app.promotion.dds_promotion_gate import build_promotion_gate_result

    settings = get_settings()
    source = "technion-math-catalog"
    mongo_database[settings.staging_degree_programs_collection].insert_one(
        {
            "sourceName": source,
            "programCode": "010001-1-000",
            "totalCredits": 155.0,
            "catalogVersion": "2025-2026",
            "isStaging": True,
            "productionEligible": False,
            "signoffReview": {"reviewStatus": "ok"},
            "curationReport": {"vaultSignoff": {"signoffSource": "manual"}},
        }
    )
    mongo_database[settings.staging_catalog_path_options_collection].insert_many(
        [
            {
                "sourceName": source,
                "optionKey": "track-math-a",
                "facultyId": "faculty-math",
                "stagingKey": "math:path:a",
            },
            {
                "sourceName": source,
                "optionKey": "track-physics-a",
                "facultyId": "faculty-physics",
                "stagingKey": "math:path:physics",
            },
        ]
    )
    mongo_database[settings.staging_catalog_faculties_collection].insert_many(
        [
            {"sourceName": source, "facultyId": "faculty-math", "stagingKey": "math:faculty"},
            {"sourceName": source, "facultyId": "faculty-physics", "stagingKey": "physics:faculty"},
        ]
    )
    mongo_database[settings.staging_courses_collection].insert_one(
        {"sourceName": "technion-course-json", "courseNumber": "01000101"}
    )
    mongo_database[settings.staging_course_offerings_collection].insert_one(
        {"courseNumber": "01000101", "stagingKey": "technion:offering:01000101"}
    )
    gate = build_promotion_gate_result(
        mongo_database,
        settings=settings,
        faculty_id="math",
        allow_warnings=True,
    )
    assert len(gate.plannedWrites.catalogPathOptions) == 1
    assert gate.plannedWrites.catalogPathOptions[0].identifier == "track-math-a"
    assert len(gate.plannedWrites.catalogFaculties) == 1
    assert gate.plannedWrites.catalogFaculties[0].identifier == "faculty-math"


def test_build_track_program_code_map_skips_missing_pages(monkeypatch) -> None:
    from app.vault.export_faculty_vault_catalog import build_track_program_code_map

    monkeypatch.setattr(
        "app.vault.export_faculty_vault_catalog.discover_faculty_track_slugs",
        lambda pages, faculty_id: ["missing-track"],
    )
    assert build_track_program_code_map({}, "math") == {}


def test_extract_program_code_falls_back_to_body_pattern(monkeypatch) -> None:
    from app.vault.export_faculty_vault_catalog import extract_program_code
    from app.vault.loader import WikiPage

    monkeypatch.setattr(
        "app.vault.export_faculty_vault_catalog.extract_field",
        lambda text, label: None,
    )
    page = WikiPage(
        slug="track-test",
        path=Path("/tmp/track-test.md"),
        frontmatter={},
        body="",
        english_body="**Program code:** 010001-1-000\n",
    )
    assert extract_program_code(page) == "010001-1-000"


def test_extract_program_code_falls_back_to_body_pattern_when_english_body_empty(monkeypatch) -> None:
    from app.vault.export_faculty_vault_catalog import extract_program_code
    from app.vault.loader import WikiPage

    monkeypatch.setattr(
        "app.vault.export_faculty_vault_catalog.extract_field",
        lambda text, label: None,
    )
    page = WikiPage(
        slug="track-test",
        path=Path("/tmp/track-test.md"),
        frontmatter={},
        body="**Program code:** 010002-1-000\n",
        english_body="",
    )
    assert extract_program_code(page) == "010002-1-000"


def test_build_generic_program_splits_technion_wide_electives_into_standard_buckets() -> None:
    from app.paths import catalog_vault_root
    from app.vault.loader import load_pages_by_slug, wiki_root

    pages = load_pages_by_slug(wiki_root(catalog_vault_root()))
    page = pages["track-computer-science-general-4year"]
    program = build_generic_program(page, faculty_id="computer-science", pages=pages)
    assert program is not None
    group_ids = {group["groupId"] for group in program["requirementGroups"]}
    code = program["programCode"]
    assert f"{code}:technion-wide-electives" not in group_ids
    assert f"{code}:enrichment" in group_ids
    assert f"{code}:free-elective" in group_ids
    assert f"{code}:physical-education" in group_ids
    assert f"{code}:enrichment-pool" in group_ids

    from app.vault.export_dds_catalog import technion_wide_elective_credit_split

    assert technion_wide_elective_credit_split(12.0) == (6.0, 4.0, 2.0)
    assert technion_wide_elective_credit_split(10.0) == (6.0, 2.0, 2.0)


@pytest.mark.parametrize("total", [12.0, 10.0, 8.0, 7.0, 6.0, 2.0, 0.0])
def test_the_technion_wide_split_never_hands_out_more_than_it_was_given(total: float) -> None:
    """`027197-1-000` states a 6-credit university-wide block, physical education
    included. The old split gave it 6 enrichment AND 2 PE regardless, inventing
    2 credits the catalogue never granted."""
    from app.vault.export_dds_catalog import technion_wide_elective_credit_split

    enrichment, free, physical = technion_wide_elective_credit_split(total)

    assert round(enrichment + free + physical, 2) == total
    assert min(enrichment, free, physical) >= 0.0


def test_a_negative_technion_wide_total_splits_to_nothing() -> None:
    from app.vault.export_dds_catalog import technion_wide_elective_credit_split

    assert technion_wide_elective_credit_split(-5.0) == (0.0, 0.0, 0.0)


@pytest.mark.parametrize(
    "slug",
    [
        "technion-wide-electives",
        "general-technion-electives",
        "technion-wide-electives-incl-2-pe",
    ],
)
def test_every_wording_of_the_university_wide_block_is_recognised(slug: str) -> None:
    """Each faculty names this block in its own words. Matching only the first
    spelling left the others standing beside the buckets that replace them, and
    counted the same credits twice."""
    from app.vault.export_faculty_vault_catalog import _is_technion_wide_aggregate_slug

    assert _is_technion_wide_aggregate_slug(slug)


@pytest.mark.parametrize("slug", ["faculty-electives", "required-courses", "enrichment"])
def test_ordinary_buckets_are_not_mistaken_for_the_university_wide_block(slug: str) -> None:
    from app.vault.export_faculty_vault_catalog import _is_technion_wide_aggregate_slug

    assert not _is_technion_wide_aggregate_slug(slug)


def test_of_which_rows_are_a_breakdown_not_extra_requirements() -> None:
    """`— of which: Enrichment | 6.0` itemises the row above it. Promoting those
    rows gave 033033 and 033133 a second copy of the same 12 credits."""
    from app.vault.export_faculty_vault_catalog import _is_bucket_breakdown_slug

    assert _is_bucket_breakdown_slug("of-which-enrichment")
    assert _is_bucket_breakdown_slug("of-which-physical-education")
    assert not _is_bucket_breakdown_slug("enrichment")


def _distribution_page(distribution: str, *, english_body: str | None = None) -> WikiPage:
    return WikiPage(
        slug="track-test",
        path=Path("/tmp/track-test.md"),
        frontmatter={},
        body="",
        english_body=english_body
        if english_body is not None
        else f"**Distribution:** {distribution}\n",
    )


def test_a_distribution_line_becomes_credit_buckets_when_there_is_no_table() -> None:
    """`021025-1-000` has a course list and no credit table, so the export gave it
    12 credits of a 155-credit degree. Its distribution line states the same
    breakdown a table would."""
    from app.vault.export_faculty_vault_catalog import parse_credit_buckets_from_distribution

    buckets = parse_credit_buckets_from_distribution(
        _distribution_page("124.5 required | 18.5 track electives | 6 enrichment | 2 PE | 4 general electives")
    )

    assert {slug: credits for _, slug, _, credits in buckets} == {
        "required-courses": 124.5,
        "track-electives": 18.5,
        "enrichment": 6.0,
        "physical-education": 2.0,
        "free-elective": 4.0,
    }
    assert sum(credits for *_, credits in buckets) == 155.0


def test_the_standard_slugs_are_reused_so_the_trio_is_not_added_twice() -> None:
    """If the line's enrichment/PE/general rows landed on their own slugs, the
    standard buckets would be added on top and the degree would overshoot by 12."""
    from app.vault.export_faculty_vault_catalog import (
        _STANDARD_TECHNION_BUCKET_SLUGS,
        parse_credit_buckets_from_distribution,
    )

    buckets = parse_credit_buckets_from_distribution(
        _distribution_page("120 required | 23 track electives | 6 enrichment | 2 PE | 4 general electives")
    )

    assert _STANDARD_TECHNION_BUCKET_SLUGS <= {slug for _, slug, _, _ in buckets}


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("track electives", "track-electives"),
        ("general electives", "free-elective"),
        ("free electives", "free-elective"),
        ("PE", "physical-education"),
        ("physical education", "physical-education"),
        ("enrichment", "enrichment"),
        ("required", "required-courses"),
        ("electives", "faculty-electives"),
    ],
)
def test_distribution_labels_resolve_to_the_right_bucket(label: str, expected: str) -> None:
    """"track electives" and "general electives" both contain "electives", so
    order of matching decides whether they land on the right bucket."""
    from app.vault.export_faculty_vault_catalog import _distribution_bucket_slug

    assert _distribution_bucket_slug(label) == expected


def test_an_unrecognised_distribution_label_is_skipped_not_guessed() -> None:
    from app.vault.export_faculty_vault_catalog import (
        _distribution_bucket_slug,
        parse_credit_buckets_from_distribution,
    )

    assert _distribution_bucket_slug("quantum widgets") is None
    buckets = parse_credit_buckets_from_distribution(
        _distribution_page("12 quantum widgets | 6 enrichment")
    )
    assert [slug for _, slug, _, _ in buckets] == ["enrichment"]


def test_a_segment_without_a_number_is_skipped() -> None:
    from app.vault.export_faculty_vault_catalog import parse_credit_buckets_from_distribution

    buckets = parse_credit_buckets_from_distribution(
        _distribution_page("see the catalog | 6 enrichment")
    )

    assert [slug for _, slug, _, _ in buckets] == ["enrichment"]


def test_a_repeated_bucket_is_taken_once() -> None:
    from app.vault.export_faculty_vault_catalog import parse_credit_buckets_from_distribution

    buckets = parse_credit_buckets_from_distribution(
        _distribution_page("6 enrichment | 4 enrichment")
    )

    assert [credits for *_, credits in buckets] == [6.0]


def test_a_page_with_no_distribution_line_yields_nothing() -> None:
    from app.vault.export_faculty_vault_catalog import parse_credit_buckets_from_distribution

    assert parse_credit_buckets_from_distribution(_distribution_page("", english_body="")) == []


def test_a_credit_table_still_wins_over_the_distribution_line() -> None:
    """The fallback must not override a page that states its buckets properly."""
    from app.vault.export_faculty_vault_catalog import parse_credit_buckets_from_page

    page = _distribution_page(
        "",
        english_body=(
            "**Distribution:** 99 required\n\n"
            "| Category | Credits |\n|---|---|\n| Required courses | 120 |\n"
        ),
    )

    assert [credits for *_, credits in parse_credit_buckets_from_page(page)] == [120.0]


def _collapse_program(wiki_page: str, kind: str, groups: list[dict]) -> dict:
    return {
        "programCode": "023044-1-000",
        "metadata": {"wikiPage": wiki_page, "programKind": kind},
        "requirementGroups": groups,
    }


def _rule(group_id: str, rule_type: str, credits: float | None = None) -> dict:
    return {
        "groupId": f"023044-1-000:{group_id}",
        "minCredits": credits,
        "ruleExpression": {"type": rule_type},
    }


def test_a_specialization_does_not_add_credit_buckets_to_the_track_it_shares_a_code_with() -> None:
    """Cyber, data-ml and bioinformatics have no program code of their own, so each
    borrows a parent track's. Merging data-ml's 12.0 "מקצועות ליבה" into the 3-year
    general track pushed a program that reconciles at 118.5 twelve credits over."""
    from app.vault.export_faculty_vault_catalog import _collapse_programs_by_code

    canonical = _collapse_program(
        "track-computer-science-general-3year", "bsc", [_rule("required", "credit_bucket", 84.0)]
    )
    specialization = _collapse_program(
        "track-computer-science-data-ml", "bsc_specialization", [_rule("core", "credit_bucket", 12.0)]
    )

    collapsed = _collapse_programs_by_code([canonical, specialization])

    assert len(collapsed) == 1
    slugs = {g["groupId"].split(":", 1)[-1] for g in collapsed[0]["requirementGroups"]}
    assert slugs == {"required"}


def test_a_specialization_still_contributes_its_course_pools() -> None:
    """Its course lists are real options for the parent degree; only the credit
    arithmetic is the canonical page's to state."""
    from app.vault.export_faculty_vault_catalog import _collapse_programs_by_code

    collapsed = _collapse_programs_by_code(
        [
            _collapse_program(
                "track-computer-science-general-3year", "bsc", [_rule("required", "credit_bucket", 84.0)]
            ),
            _collapse_program(
                "track-computer-science-data-ml",
                "bsc_specialization",
                [_rule("ml-pool", "course_pool"), _rule("core", "credit_bucket", 12.0)],
            ),
        ]
    )

    slugs = {g["groupId"].split(":", 1)[-1] for g in collapsed[0]["requirementGroups"]}
    assert slugs == {"required", "ml-pool"}


def test_a_program_that_shares_its_code_with_nobody_keeps_everything() -> None:
    from app.vault.export_faculty_vault_catalog import _collapse_programs_by_code

    only = _collapse_program(
        "track-computer-science-general-3year",
        "bsc",
        [_rule("required", "credit_bucket", 84.0), _rule("matrix", "semester_matrix")],
    )

    collapsed = _collapse_programs_by_code([only])

    assert len(collapsed[0]["requirementGroups"]) == 2


def test_cs_three_year_reconciles_with_its_own_stated_total() -> None:
    """023044-1-000 states 84.0 + 24.5 + 10.0 = 118.5 and was exporting 130.5."""
    from app.vault.vault_export_registry import export_vault_catalog

    document, _ = export_vault_catalog(faculty="computer-science")
    program = next(p for p in document["programs"] if p["programCode"] == "023044-1-000")

    bucket_total = sum(
        float(group.get("minCredits") or 0)
        for group in program["requirementGroups"]
        if (group.get("ruleExpression") or {}).get("type") == "credit_bucket"
    )

    assert round(bucket_total, 2) == program["totalCredits"] == 118.5


def _hebrew_table_page(rows: str, code: str = "021095-1-000") -> WikiPage:
    return WikiPage(
        slug="track-test",
        path=Path("/tmp/track-test.md"),
        frontmatter={},
        body="",
        english_body=(
            f"**Program code:** {code}\n**Total Credits:** 155.0\n\n"
            "| Category | Credits |\n|----------|---------|\n" + rows
        ),
    )


def _buckets_by_slug(program: dict) -> dict[str, float]:
    return {
        group["groupId"].split(":", 1)[-1]: float(group.get("minCredits") or 0)
        for group in program["requirementGroups"]
        if (group.get("ruleExpression") or {}).get("type") == "credit_bucket"
    }


def test_a_technion_wide_row_beside_itemised_parts_is_the_free_elective() -> None:
    """The four education teaching tracks list enrichment and PE as their own
    rows, so their 4.0 "בחירה כלל טכניונית" row is the remainder, not the whole
    block. Splitting it as the whole block gave them a 0.0-credit free elective."""
    page = _hebrew_table_page(
        "| מקצועות חובה | 106.5 |\n"
        "| מקצועות בחירה מומלצת | 36.5 |\n"
        "| מקצועות העשרה | 6.0 |\n"
        "| מקצועות בחירה כלל טכניונית | 4.0 |\n"
        "| חינוך גופני | 2.0 |\n"
    )

    program = build_generic_program(page, faculty_id="education-science-technology", pages={})
    assert program is not None
    buckets = _buckets_by_slug(program)

    assert buckets["free-elective"] == 4.0
    assert buckets["enrichment"] == 6.0
    assert buckets["physical-education"] == 2.0
    assert round(sum(buckets.values()), 2) == 155.0


def test_a_technion_wide_row_alone_is_still_split_into_the_three_buckets() -> None:
    """Without itemised parts the row IS the whole block, and must still split."""
    page = _hebrew_table_page(
        "| מקצועות חובה | 143.0 |\n| מקצועות בחירה כלל טכניונית | 12.0 |\n"
    )

    program = build_generic_program(page, faculty_id="education-science-technology", pages={})
    assert program is not None
    buckets = _buckets_by_slug(program)

    assert (buckets["enrichment"], buckets["free-elective"], buckets["physical-education"]) == (
        6.0,
        4.0,
        2.0,
    )
    assert round(sum(buckets.values()), 2) == 155.0


def test_itemised_parts_without_a_technion_wide_row_are_left_alone() -> None:
    """No aggregate row means nothing to reinterpret; the missing free elective
    still comes from the default block rather than from a phantom remainder."""
    page = _hebrew_table_page(
        "| מקצועות חובה | 147.0 |\n| מקצועות העשרה | 6.0 |\n| חינוך גופני | 2.0 |\n"
    )

    program = build_generic_program(page, faculty_id="education-science-technology", pages={})
    assert program is not None

    assert _buckets_by_slug(program)["free-elective"] == 4.0


@pytest.mark.parametrize(
    "slug",
    [
        "track-education-chemistry",
        "track-education-physics",
        "track-education-computer-science",
        "track-education-biology",
    ],
)
def test_education_teaching_tracks_reconcile(slug: str) -> None:
    """Each was exactly 4.0 short: a free-elective bucket promoted at 0.0."""
    from app.paths import catalog_vault_root
    from app.vault.loader import load_pages_by_slug, wiki_root

    pages = load_pages_by_slug(wiki_root(catalog_vault_root()))
    program = build_generic_program(
        pages[slug], faculty_id="education-science-technology", pages=pages
    )
    assert program is not None

    assert round(sum(_buckets_by_slug(program).values()), 2) == program["totalCredits"]


@pytest.mark.parametrize(
    "slug",
    ["track-education-electronics-electricity", "track-education-technology-machines"],
)
def test_education_tracks_now_describe_their_whole_degree(slug: str) -> None:
    """Both were reporting 12.0 credits of a 155.0-credit degree."""
    from app.paths import catalog_vault_root
    from app.vault.loader import load_pages_by_slug, wiki_root

    pages = load_pages_by_slug(wiki_root(catalog_vault_root()))
    program = build_generic_program(
        pages[slug], faculty_id="education-science-technology", pages=pages
    )
    assert program is not None

    bucket_total = sum(
        float(group.get("minCredits") or 0)
        for group in program["requirementGroups"]
        if (group.get("ruleExpression") or {}).get("type") == "credit_bucket"
    )

    assert round(bucket_total, 2) == program["totalCredits"] == 155.0


@pytest.mark.parametrize(
    ("slug", "faculty_id"),
    [
        ("track-medicine-bsc", "medicine"),
        ("track-biomedical-engineering", "biomedical-engineering"),
        ("track-biomedical-engineering-physics", "biomedical-engineering"),
    ],
)
def test_affected_tracks_credit_buckets_sum_to_their_stated_total(
    slug: str, faculty_id: str
) -> None:
    """These three were each exactly 12.0 over their own stated total."""
    from app.paths import catalog_vault_root
    from app.vault.loader import load_pages_by_slug, wiki_root

    pages = load_pages_by_slug(wiki_root(catalog_vault_root()))
    program = build_generic_program(pages[slug], faculty_id=faculty_id, pages=pages)
    assert program is not None

    bucket_total = sum(
        float(group.get("minCredits") or 0)
        for group in program["requirementGroups"]
        if (group.get("ruleExpression") or {}).get("type") == "credit_bucket"
    )

    assert round(bucket_total, 2) == program["totalCredits"]


def _assert_no_duplicate_group_ids(program: dict) -> None:
    from collections import Counter

    group_ids = [group["groupId"] for group in program["requirementGroups"]]
    duplicates = [group_id for group_id, count in Counter(group_ids).items() if count > 1]
    assert duplicates == []


def test_build_generic_program_dedupes_hebrew_credit_buckets_and_standard_technion_buckets() -> None:
    from app.paths import catalog_vault_root
    from app.vault.loader import load_pages_by_slug, wiki_root

    pages = load_pages_by_slug(wiki_root(catalog_vault_root()))
    education = build_generic_program(
        pages["track-education-computer-science"],
        faculty_id="education-science-technology",
        pages=pages,
    )
    mathematics = build_generic_program(
        pages["track-mathematics-bsc"],
        faculty_id="mathematics",
        pages=pages,
    )
    assert education is not None and mathematics is not None
    _assert_no_duplicate_group_ids(education)
    _assert_no_duplicate_group_ids(mathematics)
    assert any(
        group["groupId"].endswith(":required-courses")
        for group in education["requirementGroups"]
    )


def test_should_export_degree_program_skips_specializations_and_canonical_mirrors() -> None:
    from app.paths import catalog_vault_root
    from app.vault.export_faculty_vault_catalog import discover_faculty_track_slugs
    from app.vault.loader import load_pages_by_slug, wiki_root

    pages = load_pages_by_slug(wiki_root(catalog_vault_root()))
    assert should_export_degree_program(pages["track-biology-general"]) is True
    assert should_export_degree_program(pages["track-biology-human-development"]) is True
    assert should_export_degree_program(pages["track-computer-science-cyber"]) is False
    assert should_export_degree_program(pages["track-medicine-dual-computer-science"]) is False

    medicine_slugs = frozenset(discover_faculty_track_slugs(pages, "medicine"))
    assert should_export_degree_program(
        pages["track-medicine-dual-computer-science"],
        faculty_track_slugs=medicine_slugs,
    ) is False
    assert should_export_degree_program(
        pages["track-medicine-dual-biomedical-engineering"],
        faculty_track_slugs=medicine_slugs,
        pages=pages,
    ) is False

    chemistry_slugs = frozenset(discover_faculty_track_slugs(pages, "chemistry"))
    assert should_export_degree_program(
        pages["track-chemistry-materials-combined"],
        faculty_track_slugs=chemistry_slugs,
        pages=pages,
    ) is False


def test_should_export_degree_program_skips_non_primary_canonical_with_faculty_slugs(
    monkeypatch,
) -> None:
    page = WikiPage(
        slug="track-mirror",
        path=Path("/tmp/mirror.md"),
        frontmatter={"canonicalSlug": "track-canonical"},
        body="",
        english_body="",
    )
    monkeypatch.setattr(
        "app.vault.export_faculty_vault_catalog._track_selectable_as_primary",
        lambda candidate: False,
    )
    assert should_export_degree_program(
        page,
        faculty_track_slugs=frozenset({"track-mirror"}),
    ) is False


def test_should_export_degree_program_exports_mirror_when_canonical_page_missing() -> None:
    page = WikiPage(
        slug="track-mirror",
        path=Path("/tmp/mirror.md"),
        frontmatter={"canonicalSlug": "track-canonical"},
        body="",
        english_body="",
    )
    pages = {"track-mirror": page}
    assert should_export_degree_program(
        page,
        faculty_track_slugs=frozenset({"track-mirror"}),
        pages=pages,
    ) is True


def test_export_biology_expected_program_codes_match_per_track_programs() -> None:
    biology_doc, _ = export_faculty_vault_catalog(faculty_id="biology")
    program_codes = [program["programCode"] for program in biology_doc["programs"]]
    assert biology_doc["source"]["expectedProgramCodes"] == sorted(program_codes)
    assert "013043-1-000" in program_codes
    exported_slugs = biology_doc["parserReport"]["trackPagesExported"]
    assert "track-biology-general" in exported_slugs
    assert "track-biology-human-development" in exported_slugs


def test_export_cross_faculty_canonical_mirrors_have_elective_pools() -> None:
    """Canonical dual-degree tracks export once from the owning faculty with elective pools."""
    materials_doc, _ = export_faculty_vault_catalog(faculty_id="materials-science-engineering")
    materials_program = next(
        program
        for program in materials_doc["programs"]
        if (program.get("metadata") or {}).get("wikiPage") == "track-materials-engineering-chemistry"
    )
    materials_pools = [
        group
        for group in materials_program.get("requirementGroups") or []
        if (group.get("ruleExpression") or {}).get("operator") in {"choose_n", "choose_chain"}
        and (group.get("courseReferences") or [])
    ]
    assert materials_pools

    biomedical_doc, _ = export_faculty_vault_catalog(faculty_id="biomedical-engineering")
    biomedical_program = next(
        program
        for program in biomedical_doc["programs"]
        if (program.get("metadata") or {}).get("wikiPage")
        == "track-biomedical-engineering-medicine-dual"
    )
    biomedical_pools = [
        group
        for group in biomedical_program.get("requirementGroups") or []
        if (group.get("ruleExpression") or {}).get("operator") in {"choose_n", "choose_chain"}
        and (group.get("courseReferences") or [])
    ]
    assert biomedical_pools


def test_export_faculty_vault_catalog_exports_each_primary_track_slug(
    monkeypatch,
) -> None:
    """Each exportable track slug is recorded; shared program codes collapse to one document."""
    program_code = "099999-1-000"
    pages = {
        "track-dup-a": WikiPage(
            slug="track-dup-a",
            path=Path("/tmp/track-dup-a.md"),
            frontmatter={"faculty": "faculty-test"},
            body="",
            english_body=f"**Track code:** {program_code}\n",
        ),
        "track-dup-b": WikiPage(
            slug="track-dup-b",
            path=Path("/tmp/track-dup-b.md"),
            frontmatter={"faculty": "faculty-test"},
            body="",
            english_body=f"**Track code:** {program_code}\n",
        ),
    }
    monkeypatch.setattr(
        "app.vault.export_faculty_vault_catalog.load_pages_by_slug",
        lambda root: pages,
    )
    monkeypatch.setattr(
        "app.vault.export_faculty_vault_catalog.discover_faculty_track_slugs",
        lambda loaded_pages, faculty_id: ["track-dup-a", "track-dup-b"],
    )
    monkeypatch.setattr(
        "app.vault.export_faculty_vault_catalog.build_generic_program",
        lambda page, faculty_id, pages: {
            "programCode": program_code,
            "metadata": {"wikiPage": page.slug},
            "requirementGroups": [],
            "totalCredits": 155.0,
        },
    )
    monkeypatch.setattr(
        "app.vault.export_faculty_vault_catalog.build_wiki_path_catalog",
        lambda **kwargs: {"faculties": [], "pathOptions": []},
    )
    monkeypatch.setattr(
        "app.vault.export_faculty_vault_catalog.apply_vault_signoff_to_catalog",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "app.vault.export_faculty_vault_catalog.build_readiness_after_vault_signoff",
        lambda doc: {
            "counts": {},
            "blockingIssuesForStaging": [],
            "canImportToStaging": True,
        },
    )
    monkeypatch.setattr(
        "app.vault.export_faculty_vault_catalog.ReviewedCuratedCatalogDocument.model_validate",
        lambda doc: doc,
    )
    monkeypatch.setattr(
        "app.vault.export_faculty_vault_catalog.Phase8ReadinessCheck.model_validate",
        lambda readiness: readiness,
    )
    doc, _ = export_faculty_vault_catalog(faculty_id="test")
    assert len(doc["programs"]) == 1
    assert doc["parserReport"]["trackPagesExported"] == ["track-dup-a", "track-dup-b"]
    assert doc["programs"][0]["metadata"]["wikiPage"] == "track-dup-a"


def test_export_faculty_vault_catalog_exports_shared_code_per_track_slug() -> None:
    biology_doc, _ = export_faculty_vault_catalog(faculty_id="biology")
    biology_slugs = {(program["programCode"], program["metadata"]["wikiPage"]) for program in biology_doc["programs"]}
    assert ("013043-1-000", "track-biology-general") in biology_slugs
    assert "track-biology-human-development" in biology_doc["parserReport"]["trackPagesExported"]
    assert len(biology_doc["programs"]) >= 2

    cs_doc, _ = export_faculty_vault_catalog(faculty_id="computer-science")
    cs_slugs = [program["metadata"]["wikiPage"] for program in cs_doc["programs"]]
    assert "track-computer-science-general-3year" in cs_slugs
    assert "track-computer-science-general-4year" in cs_slugs
    assert len(cs_doc["programs"]) >= 7


def test_export_faculty_vault_catalog_skips_duplicate_slug(monkeypatch) -> None:
    program_code = "099998-1-000"
    page = WikiPage(
        slug="track-once",
        path=Path("/tmp/track-once.md"),
        frontmatter={"faculty": "faculty-test"},
        body="",
        english_body=f"**Track code:** {program_code}\n",
    )
    monkeypatch.setattr(
        "app.vault.export_faculty_vault_catalog.load_pages_by_slug",
        lambda root: {"track-once": page},
    )
    monkeypatch.setattr(
        "app.vault.export_faculty_vault_catalog.discover_faculty_track_slugs",
        lambda loaded_pages, faculty_id: ["track-once", "track-once"],
    )
    monkeypatch.setattr(
        "app.vault.export_faculty_vault_catalog.build_wiki_path_catalog",
        lambda **kwargs: {"faculties": [], "pathOptions": []},
    )
    monkeypatch.setattr(
        "app.vault.export_faculty_vault_catalog.apply_vault_signoff_to_catalog",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "app.vault.export_faculty_vault_catalog.build_readiness_after_vault_signoff",
        lambda doc: {
            "counts": {},
            "blockingIssuesForStaging": [],
            "canImportToStaging": True,
        },
    )
    monkeypatch.setattr(
        "app.vault.export_faculty_vault_catalog.ReviewedCuratedCatalogDocument.model_validate",
        lambda doc: doc,
    )
    monkeypatch.setattr(
        "app.vault.export_faculty_vault_catalog.Phase8ReadinessCheck.model_validate",
        lambda readiness: readiness,
    )
    doc, _ = export_faculty_vault_catalog(faculty_id="test")
    assert len(doc["programs"]) == 1


def test_build_course_reference_parses_slash_separated_alternatives() -> None:
    from app.vault.export_dds_catalog import build_course_reference

    ref = build_course_reference("00440252 / 02340252", title_hint="Digital systems")
    assert ref is not None
    assert ref["courseNumber"] == "02340252"
    assert any("00440252" in str(note) for note in (ref.get("notes") or []))


def test_semester_matrix_groups_merge_variant_headings() -> None:
    from app.paths import catalog_vault_root
    from app.vault.export_dds_catalog import _semester_matrix_groups
    from app.vault.loader import load_pages_by_slug, wiki_root

    pages = load_pages_by_slug(wiki_root(catalog_vault_root()))
    page = pages["track-electrical-engineering-physics"]
    groups = _semester_matrix_groups(page, "004141-1-000")
    semester_six = [group for group in groups if group["groupId"].endswith("semester-6-matrix")]
    assert len(semester_six) == 1
    assert len(semester_six[0]["courseReferences"]) > 0


def test_semester_matrix_groups_parse_hebrew_headings() -> None:
    from app.paths import catalog_vault_root
    from app.vault.export_dds_catalog import _semester_matrix_groups
    from app.vault.loader import load_pages_by_slug, wiki_root

    pages = load_pages_by_slug(wiki_root(catalog_vault_root()))
    page = pages["track-mechanical-engineering"]
    groups = _semester_matrix_groups(page, "034034-1-000", pages=pages)
    assert len(groups) >= 6


def test_semester_matrices_inherit_from_elective_source() -> None:
    from app.paths import catalog_vault_root
    from app.vault.export_faculty_vault_catalog import _semester_matrices_for_track
    from app.vault.loader import load_pages_by_slug, wiki_root

    pages = load_pages_by_slug(wiki_root(catalog_vault_root()))
    barak = pages["track-mechanical-engineering-barak"]
    groups = _semester_matrices_for_track(barak, "034034-2-000", pages)
    assert len(groups) >= 6
    assert all(group["groupId"].startswith("034034-2-000:") for group in groups)


def test_cs_3year_semester_matrices_merge_parent_and_local() -> None:
    from app.paths import catalog_vault_root
    from app.vault.export_faculty_vault_catalog import _semester_matrices_for_track
    from app.vault.loader import load_pages_by_slug, wiki_root

    pages = load_pages_by_slug(wiki_root(catalog_vault_root()))
    cs_3year = pages["track-computer-science-general-3year"]
    groups = _semester_matrices_for_track(cs_3year, "023044-1-000", pages)
    semesters = sorted(
        int((group.get("ruleExpression") or {}).get("semester") or 0) for group in groups
    )
    assert semesters == [1, 2, 3, 4, 5]
    semester_one = next(group for group in groups if group["groupId"].endswith("semester-1-matrix"))
    semester_one_numbers = {
        ref["courseNumber"] for ref in semester_one.get("courseReferences") or []
    }
    assert "01040031" in semester_one_numbers
    assert "01340058" not in semester_one_numbers

    semester_four = next(group for group in groups if group["groupId"].endswith("semester-4-matrix"))
    semester_four_numbers = {
        ref["courseNumber"] for ref in semester_four.get("courseReferences") or []
    }
    assert "02340118" in semester_four_numbers
    assert "01340058" not in semester_four_numbers
    assert "01250001" not in semester_four_numbers

    semester_five = next(group for group in groups if group["groupId"].endswith("semester-5-matrix"))
    semester_five_numbers = {
        ref["courseNumber"] for ref in semester_five.get("courseReferences") or []
    }
    assert {"02360343", "02360267"} <= semester_five_numbers


def test_cs_export_collapses_duplicate_program_code_to_general_track_matrix() -> None:
    from app.paths import catalog_vault_root
    from app.vault.export_faculty_vault_catalog import export_faculty_vault_catalog
    from app.vault.loader import load_pages_by_slug, wiki_root

    pages = load_pages_by_slug(wiki_root(catalog_vault_root()))
    document, _ = export_faculty_vault_catalog(faculty_id="computer-science")
    cs_programs = [program for program in document["programs"] if program["programCode"] == "023044-1-000"]
    assert len(cs_programs) == 1
    assert (cs_programs[0].get("metadata") or {}).get("wikiPage") == "track-computer-science-general-3year"
    matrices = [
        group
        for group in cs_programs[0].get("requirementGroups", [])
        if (group.get("ruleExpression") or {}).get("type") == "semester_matrix"
    ]
    semesters = sorted(int((group.get("ruleExpression") or {}).get("semester") or 0) for group in matrices)
    assert semesters == [1, 2, 3, 4, 5]
    semester_four = next(group for group in matrices if group["groupId"].endswith("semester-4-matrix"))
    assert {ref["courseNumber"] for ref in semester_four.get("courseReferences") or []} == {
        "02340118",
        "02340123",
        "02340247",
    }
