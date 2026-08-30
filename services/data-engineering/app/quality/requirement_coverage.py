"""Measure how much of each degree the promoted requirement buckets actually describe.

Graduation progress is computed from `degree_requirements`, whose only executable
rule type is `credit_bucket`. Everything more expressive the importer produced --
`choose_n`, `min_credits`, `choose_chain` -- is promoted to `catalog_rules` as
advisory and never reaches a student's progress page.

For most programs that is harmless: the credit buckets carry the whole degree and
the pools only say which courses may fill them. For some it is not. A program
whose buckets sum to 12 credits against a stated 155 has no row for the other 143,
so a student's core coursework lands in `not_assigned_to_requirement` instead of
counting toward anything.

This module reports that gap per program. It decides nothing: closing a gap means
choosing what the missing buckets are, and that is a catalogue judgement about a
specific track, not something to infer from a subtraction.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pymongo.database import Database

from app.config import Settings, get_settings
from app.paths import service_root

# Credit sums are rounded to half-points upstream, so anything under this is a
# rounding artefact rather than a missing requirement.
COVERAGE_TOLERANCE_CREDITS = 0.5

# Below this share of the stated total, the buckets are not describing the degree
# at all -- they are the leftovers that happened to promote. Above it, the shape
# is right and the disagreement is an accounting one.
STRUCTURAL_COVERAGE_RATIO = 0.5

EXECUTABLE_RULE_TYPE = "credit_bucket"
POOL_RULE_TYPE = "course_pool"


@dataclass(frozen=True)
class ProgramCoverage:
    """One program's promoted buckets measured against its stated total."""

    program_code: str
    name: str | None
    total_credits: float | None
    promoted_group_count: int
    promoted_credits: float
    quarantined_pool_count: int
    quarantined_operators: tuple[tuple[str, int], ...]
    quarantined_with_course_refs: int

    @property
    def gap_credits(self) -> float | None:
        if self.total_credits is None:
            return None
        return round(self.total_credits - self.promoted_credits, 2)

    @property
    def coverage_ratio(self) -> float | None:
        if not self.total_credits:
            return None
        return round(self.promoted_credits / self.total_credits, 4)

    @property
    def status(self) -> str:
        """`unknown` when the program states no total to measure against."""
        gap = self.gap_credits
        if gap is None:
            return "unknown"
        if abs(gap) <= COVERAGE_TOLERANCE_CREDITS:
            return "covered"
        if gap < 0:
            return "over"
        ratio = self.coverage_ratio
        if ratio is not None and ratio < STRUCTURAL_COVERAGE_RATIO:
            return "structural"
        return "under"

    def to_dict(self) -> dict[str, Any]:
        return {
            "programCode": self.program_code,
            "name": self.name,
            "totalCredits": self.total_credits,
            "promotedGroupCount": self.promoted_group_count,
            "promotedCredits": self.promoted_credits,
            "gapCredits": self.gap_credits,
            "coverageRatio": self.coverage_ratio,
            "status": self.status,
            "quarantinedPoolCount": self.quarantined_pool_count,
            "quarantinedOperators": dict(self.quarantined_operators),
            "quarantinedWithCourseRefs": self.quarantined_with_course_refs,
        }


@dataclass(frozen=True)
class RequirementCoverageResult:
    programs: tuple[ProgramCoverage, ...]
    duplicate_program_codes: tuple[str, ...]
    generated_at: str
    non_credit_bucket_rule_types: tuple[tuple[str, int], ...] = field(default=())

    def by_status(self, status: str) -> tuple[ProgramCoverage, ...]:
        return tuple(p for p in self.programs if p.status == status)

    def recurring_gaps(self) -> tuple[tuple[float, tuple[str, ...]], ...]:
        """Identical gaps shared by several programs, largest cohort first.

        A gap that repeats to the decimal across unrelated faculties is one
        mistake made once, not N catalogue disagreements: eight programs sitting
        at exactly -12.0 are the university-wide 6+4+2 counted twice. Grouping
        them is what turns this report into a handful of decisions.
        """
        clusters: dict[float, list[str]] = {}
        for program in self.programs:
            gap = program.gap_credits
            if gap is None or abs(gap) <= COVERAGE_TOLERANCE_CREDITS:
                continue
            clusters.setdefault(gap, []).append(program.program_code)
        return tuple(
            (gap, tuple(sorted(codes)))
            for gap, codes in sorted(clusters.items(), key=lambda kv: (-len(kv[1]), kv[0]))
            if len(codes) > 1
        )

    @property
    def status(self) -> str:
        if self.by_status("structural"):
            return "fail"
        if self.by_status("under") or self.by_status("over"):
            return "warn"
        return "pass"

    @property
    def ok(self) -> bool:
        return self.status == "pass"


def _credits(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _optional_credits(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_coverage(
    programs: list[dict[str, Any]],
    requirements: list[dict[str, Any]],
    rules: list[dict[str, Any]],
    *,
    generated_at: str | None = None,
) -> RequirementCoverageResult:
    """Pure core: given the three collections, report per-program coverage."""
    promoted_counts: Counter[str] = Counter()
    promoted_credits: dict[str, float] = {}
    for document in requirements:
        code = str(document.get("programCode") or "")
        if not code:
            continue
        promoted_counts[code] += 1
        promoted_credits[code] = promoted_credits.get(code, 0.0) + _credits(
            document.get("minCredits")
        )

    pool_counts: Counter[str] = Counter()
    pool_operators: dict[str, Counter[str]] = {}
    pool_with_refs: Counter[str] = Counter()
    rule_types: Counter[str] = Counter()
    for document in rules:
        expression = document.get("ruleExpression") or {}
        rule_type = str(expression.get("type") or "")
        rule_types[rule_type] += 1
        if rule_type != POOL_RULE_TYPE:
            continue
        code = str(document.get("programCode") or "")
        if not code:
            continue
        pool_counts[code] += 1
        operator = str(expression.get("operator") or "unknown")
        pool_operators.setdefault(code, Counter())[operator] += 1
        if document.get("courseReferences"):
            pool_with_refs[code] += 1

    seen: dict[str, dict[str, Any]] = {}
    duplicates: list[str] = []
    for program in programs:
        code = str(program.get("programCode") or "")
        if not code:
            continue
        if code in seen:
            duplicates.append(code)
            continue
        seen[code] = program

    coverages = [
        ProgramCoverage(
            program_code=code,
            name=program.get("name"),
            total_credits=_optional_credits(program.get("totalCredits")),
            promoted_group_count=promoted_counts.get(code, 0),
            promoted_credits=round(promoted_credits.get(code, 0.0), 2),
            quarantined_pool_count=pool_counts.get(code, 0),
            quarantined_operators=tuple(sorted(pool_operators.get(code, Counter()).items())),
            quarantined_with_course_refs=pool_with_refs.get(code, 0),
        )
        for code, program in sorted(seen.items())
    ]

    return RequirementCoverageResult(
        programs=tuple(coverages),
        duplicate_program_codes=tuple(sorted(set(duplicates))),
        generated_at=generated_at or datetime.now(UTC).isoformat(),
        non_credit_bucket_rule_types=tuple(sorted(rule_types.items())),
    )


def analyze_requirement_coverage(
    database: Database,
    *,
    settings: Settings | None = None,
) -> RequirementCoverageResult:
    settings = settings or get_settings()
    published = {"status": "published"}
    programs = list(
        database[settings.production_degree_programs_collection].find(
            published, {"programCode": 1, "name": 1, "totalCredits": 1}
        )
    )
    requirements = list(
        database[settings.production_degree_requirements_collection].find(
            published, {"programCode": 1, "minCredits": 1}
        )
    )
    rules = list(
        database[settings.production_catalog_rules_collection].find(
            published, {"programCode": 1, "ruleExpression": 1, "courseReferences": 1}
        )
    )
    return build_coverage(programs, requirements, rules)


def default_coverage_report_json_path() -> Path:
    return service_root() / "data" / "reports" / "technion" / "requirement_coverage_report.json"


def default_coverage_report_md_path() -> Path:
    return service_root() / "data" / "reports" / "technion" / "requirement_coverage_report.md"


def _program_table(rows: tuple[ProgramCoverage, ...]) -> list[str]:
    lines = [
        "| Program | Stated | Promoted | Gap | Groups | Pools held back |",
        "|---------|-------:|---------:|----:|-------:|----------------:|",
    ]
    for row in sorted(rows, key=lambda r: -(r.gap_credits or 0)):
        name = (row.name or "").strip() or row.program_code
        lines.append(
            f"| `{row.program_code}` {name} | {row.total_credits} | {row.promoted_credits} "
            f"| {row.gap_credits} | {row.promoted_group_count} | {row.quarantined_pool_count} |"
        )
    lines.append("")
    return lines


def render_coverage_markdown(result: RequirementCoverageResult) -> str:
    structural = result.by_status("structural")
    under = result.by_status("under")
    over = result.by_status("over")
    lines = [
        "# Requirement Coverage Report",
        "",
        f"Status: **{result.status.upper()}**",
        f"Generated: {result.generated_at}",
        "",
        "How much of each degree the promoted `credit_bucket` requirements describe.",
        "A gap means the progress page has no requirement row for those credits, so",
        "coursework that fills them is reported as counting toward nothing.",
        "",
        "## Summary",
        "",
        "| Bucket | Programs |",
        "|--------|---------:|",
        f"| Structural (under half the degree described) | {len(structural)} |",
        f"| Under (buckets sum below the stated total) | {len(under)} |",
        f"| Over (buckets sum above the stated total) | {len(over)} |",
        f"| Covered | {len(result.by_status('covered'))} |",
        f"| No stated total | {len(result.by_status('unknown'))} |",
        "",
    ]
    recurring = result.recurring_gaps()
    if recurring:
        lines += [
            "## Recurring gaps",
            "",
            "The same gap to the decimal across unrelated faculties is one rule to",
            "settle, not one decision per program.",
            "",
            "| Gap | Programs | Codes |",
            "|----:|---------:|-------|",
            *(
                f"| {gap} | {len(codes)} | {', '.join(f'`{c}`' for c in codes)} |"
                for gap, codes in recurring
            ),
            "",
        ]
    if structural:
        lines += ["## Structural gaps", "", *_program_table(structural)]
    if under:
        lines += ["## Under-described", "", *_program_table(under)]
    if over:
        lines += ["## Over-described", "", *_program_table(over)]
    if result.duplicate_program_codes:
        lines += [
            "## Duplicate program codes",
            "",
            "More than one published `degree_programs` document shares these codes:",
            "",
            *(f"- `{code}`" for code in result.duplicate_program_codes),
            "",
        ]
    if result.ok:
        lines.append("Every program's promoted buckets sum to its stated total.")
    return "\n".join(lines)


def write_coverage_report(
    result: RequirementCoverageResult,
    *,
    json_path: Path | None = None,
    md_path: Path | None = None,
) -> tuple[Path, Path]:
    out_json = json_path or default_coverage_report_json_path()
    out_md = md_path or default_coverage_report_md_path()
    out_json.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": result.status,
        "generatedAt": result.generated_at,
        "counts": {
            status: len(result.by_status(status))
            for status in ("structural", "under", "over", "covered", "unknown")
        },
        "ruleTypes": dict(result.non_credit_bucket_rule_types),
        "recurringGaps": [
            {"gapCredits": gap, "programCodes": list(codes)}
            for gap, codes in result.recurring_gaps()
        ],
        "duplicateProgramCodes": list(result.duplicate_program_codes),
        "programs": [program.to_dict() for program in result.programs],
    }
    out_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    out_md.write_text(render_coverage_markdown(result), encoding="utf-8")
    return out_json, out_md
