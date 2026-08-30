"""Unit tests for the requirement coverage analysis.

The gap this measures is real: `021025-1-000` states 155 credits and promotes
three buckets totalling 12, so 143 credits of the degree have no requirement row.
The numbers in these tests come from that program.
"""

from __future__ import annotations

import pytest

from app.quality.requirement_coverage import (
    build_coverage,
    render_coverage_markdown,
)


def _program(code="P1", total=155.0, name="Track"):
    return {"programCode": code, "name": name, "totalCredits": total}


def _requirement(code="P1", credits=6.0, group="P1:enrichment"):
    return {"programCode": code, "minCredits": credits, "requirementGroupId": group}


def _pool(code="P1", operator="choose_n", refs=3):
    return {
        "programCode": code,
        "ruleExpression": {"type": "course_pool", "operator": operator, "chooseCount": 3},
        "courseReferences": [{"courseNumber": f"0000000{i}"} for i in range(refs)],
    }


def _only(result):
    assert len(result.programs) == 1
    return result.programs[0]


def test_buckets_matching_the_stated_total_are_covered() -> None:
    result = build_coverage(
        [_program(total=10.0)],
        [_requirement(credits=6.0), _requirement(credits=4.0, group="P1:free")],
        [],
    )

    assert _only(result).status == "covered"
    assert _only(result).gap_credits == 0.0
    assert result.ok


def test_the_real_thin_program_reads_as_structural() -> None:
    """155 stated, 12 promoted -- the buckets are not describing this degree."""
    result = build_coverage(
        [_program(total=155.0)],
        [
            _requirement(credits=6.0),
            _requirement(credits=4.0, group="P1:free-elective"),
            _requirement(credits=2.0, group="P1:physical-education"),
        ],
        [_pool() for _ in range(18)],
    )

    program = _only(result)
    assert program.promoted_credits == 12.0
    assert program.gap_credits == 143.0
    assert program.status == "structural"
    assert program.quarantined_pool_count == 18
    assert result.status == "fail"


def test_a_shortfall_above_half_the_degree_is_under_not_structural() -> None:
    """The shape is right; the accounting disagrees. That is a different problem
    from a degree with no structure at all, and it gets a different label."""
    result = build_coverage([_program(total=100.0)], [_requirement(credits=90.0)], [])

    assert _only(result).status == "under"
    assert result.status == "warn"


def test_buckets_summing_above_the_total_are_flagged_too() -> None:
    result = build_coverage([_program(total=100.0)], [_requirement(credits=104.0)], [])

    assert _only(result).status == "over"
    assert _only(result).gap_credits == -4.0


@pytest.mark.parametrize("gap", [0.5, -0.5, 0.25])
def test_rounding_noise_is_not_a_gap(gap: float) -> None:
    result = build_coverage([_program(total=100.0)], [_requirement(credits=100.0 - gap)], [])

    assert _only(result).status == "covered"


def test_a_program_stating_no_total_cannot_be_measured() -> None:
    """Reporting `covered` here would be a guess dressed as a fact."""
    result = build_coverage([_program(total=None)], [_requirement(credits=12.0)], [])

    program = _only(result)
    assert program.status == "unknown"
    assert program.gap_credits is None
    assert program.coverage_ratio is None


def test_requirements_for_other_programs_do_not_count() -> None:
    result = build_coverage(
        [_program(code="P1", total=10.0)],
        [_requirement(code="P1", credits=4.0), _requirement(code="P2", credits=6.0)],
        [],
    )

    assert _only(result).promoted_credits == 4.0


def test_only_course_pool_rules_count_as_held_back() -> None:
    """A semester matrix is advisory by nature -- a recommended order, not a
    requirement -- so counting it as withheld structure would overstate the gap."""
    matrix = {
        "programCode": "P1",
        "ruleExpression": {"type": "semester_matrix"},
        "courseReferences": [{"courseNumber": "00000001"}],
    }
    result = build_coverage([_program()], [_requirement()], [_pool(), matrix])

    assert _only(result).quarantined_pool_count == 1
    assert dict(result.non_credit_bucket_rule_types)["semester_matrix"] == 1


def test_operators_and_reference_coverage_are_reported() -> None:
    """A pool with no course references cannot be promoted even if we wanted to,
    so the count of those is the part that says how much work remains."""
    empty = _pool(operator="min_credits", refs=0)
    result = build_coverage([_program()], [_requirement()], [_pool(), _pool(), empty])

    program = _only(result)
    assert dict(program.quarantined_operators) == {"choose_n": 2, "min_credits": 1}
    assert program.quarantined_with_course_refs == 2


def test_duplicate_program_codes_are_reported_not_double_counted() -> None:
    result = build_coverage(
        [_program(total=10.0), _program(total=10.0)],
        [_requirement(credits=10.0)],
        [],
    )

    assert result.duplicate_program_codes == ("P1",)
    assert _only(result).promoted_credits == 10.0


def test_a_program_with_no_requirements_at_all_is_structural() -> None:
    result = build_coverage([_program(total=155.0)], [], [])

    assert _only(result).promoted_credits == 0.0
    assert _only(result).status == "structural"


def test_markdown_names_the_programs_that_need_a_decision() -> None:
    result = build_coverage(
        [_program(code="021025-1-000", total=155.0, name="הוראת אלקטרוניקה-חשמל")],
        [_requirement(code="021025-1-000", credits=12.0)],
        [_pool(code="021025-1-000")],
    )

    markdown = render_coverage_markdown(result)
    assert "Structural gaps" in markdown
    assert "021025-1-000" in markdown
    assert "143.0" in markdown


def test_markdown_separates_under_over_and_duplicates() -> None:
    result = build_coverage(
        [
            _program(code="P1", total=100.0, name="Under"),
            _program(code="P2", total=100.0, name="Over"),
            _program(code="P2", total=100.0, name="Over duplicate"),
        ],
        [_requirement(code="P1", credits=90.0), _requirement(code="P2", credits=104.0)],
        [],
    )

    markdown = render_coverage_markdown(result)
    assert "## Under-described" in markdown
    assert "## Over-described" in markdown
    assert "## Duplicate program codes" in markdown


def test_markdown_says_so_when_everything_reconciles() -> None:
    result = build_coverage([_program(total=10.0)], [_requirement(credits=10.0)], [])

    assert "sum to its stated total" in render_coverage_markdown(result)


def test_a_row_with_no_name_falls_back_to_its_code() -> None:
    result = build_coverage(
        [_program(code="P9", total=155.0, name="  ")], [_requirement(code="P9", credits=1.0)], []
    )

    assert "P9" in render_coverage_markdown(result)


@pytest.mark.parametrize("bad", ["abc", {}, []])
def test_unparseable_bucket_credits_count_as_zero_not_a_crash(bad) -> None:
    """A malformed minCredits must not take the whole report down with it; the
    program simply reads as having nothing promoted, which is the honest result."""
    result = build_coverage([_program(total=10.0)], [_requirement(credits=bad)], [])

    assert _only(result).promoted_credits == 0.0


@pytest.mark.parametrize("bad", ["abc", {}])
def test_an_unparseable_stated_total_is_unknown_not_zero(bad) -> None:
    result = build_coverage([_program(total=bad)], [_requirement(credits=10.0)], [])

    assert _only(result).status == "unknown"


def test_documents_without_a_program_code_are_ignored() -> None:
    result = build_coverage(
        [_program(total=10.0), {"name": "orphan", "totalCredits": 5.0}],
        [_requirement(credits=10.0), {"minCredits": 99.0}],
        [_pool(), {"ruleExpression": {"type": "course_pool", "operator": "choose_n"}}],
    )

    program = _only(result)
    assert program.promoted_credits == 10.0
    assert program.quarantined_pool_count == 1


def test_analysis_reads_the_published_production_collections(mongo_database) -> None:
    from app.quality.requirement_coverage import analyze_requirement_coverage

    mongo_database.degree_programs.insert_many(
        [
            {"programCode": "P1", "name": "Track", "totalCredits": 155.0, "status": "published"},
            {"programCode": "P2", "name": "Draft", "totalCredits": 10.0, "status": "draft"},
        ]
    )
    mongo_database.degree_requirements.insert_one(
        {"programCode": "P1", "minCredits": 12.0, "status": "published"}
    )
    mongo_database.catalog_rules.insert_one(
        {
            "programCode": "P1",
            "ruleExpression": {"type": "course_pool", "operator": "choose_n"},
            "courseReferences": [{"courseNumber": "00000001"}],
            "status": "published",
        }
    )

    result = analyze_requirement_coverage(mongo_database)

    assert [p.program_code for p in result.programs] == ["P1"]
    assert _only(result).gap_credits == 143.0
    assert _only(result).quarantined_pool_count == 1


def test_report_is_written_as_both_json_and_markdown(tmp_path) -> None:
    import json

    from app.quality.requirement_coverage import write_coverage_report

    result = build_coverage(
        [_program(code="021025-1-000", total=155.0)],
        [_requirement(code="021025-1-000", credits=12.0)],
        [_pool(code="021025-1-000")],
    )

    json_path, md_path = write_coverage_report(
        result, json_path=tmp_path / "c.json", md_path=tmp_path / "c.md"
    )

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["status"] == "fail"
    assert payload["counts"]["structural"] == 1
    assert payload["programs"][0]["gapCredits"] == 143.0
    assert payload["programs"][0]["quarantinedOperators"] == {"choose_n": 1}
    assert "021025-1-000" in md_path.read_text(encoding="utf-8")


def test_programs_sharing_a_gap_are_grouped_into_one_decision() -> None:
    """Eight real programs sit at exactly -12.0 -- the university-wide 6+4+2
    counted twice. That is one rule to settle, so the report must group them."""
    result = build_coverage(
        [_program(code=f"P{i}", total=100.0) for i in range(3)] + [_program(code="P9", total=100.0)],
        [_requirement(code=f"P{i}", credits=112.0) for i in range(3)]
        + [_requirement(code="P9", credits=80.0)],
        [],
    )

    recurring = result.recurring_gaps()

    assert recurring == ((-12.0, ("P0", "P1", "P2")),)
    assert "Recurring gaps" in render_coverage_markdown(result)


def test_a_gap_unique_to_one_program_is_not_a_cluster() -> None:
    result = build_coverage(
        [_program(code="P1", total=100.0), _program(code="P2", total=100.0)],
        [_requirement(code="P1", credits=80.0), _requirement(code="P2", credits=70.0)],
        [],
    )

    assert result.recurring_gaps() == ()
    assert "Recurring gaps" not in render_coverage_markdown(result)


def test_programs_that_reconcile_are_never_clustered() -> None:
    """Three programs all at gap 0 are three correct programs, not a cohort."""
    result = build_coverage(
        [_program(code=f"P{i}", total=100.0) for i in range(3)],
        [_requirement(code=f"P{i}", credits=100.0) for i in range(3)],
        [],
    )

    assert result.recurring_gaps() == ()


def test_default_report_paths_sit_with_the_other_technion_reports() -> None:
    from app.quality.requirement_coverage import (
        default_coverage_report_json_path,
        default_coverage_report_md_path,
    )

    assert default_coverage_report_json_path().parent.name == "technion"
    assert default_coverage_report_md_path().name.endswith(".md")
