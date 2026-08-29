"""Per-course outcome statistics, aggregated from UniPilot's own transcripts.

What this is for
----------------
The planner could rank candidates only by curriculum position and credits: it
had no idea which courses students actually struggle with. `01040166` has a
67% pass rate and a 57.8 mean across the transcripts we hold -- a student
planning a heavy term deserves to see that, and a tie between two otherwise
equal electives is better broken by evidence than by course number.

Two sources, kept apart
-----------------------
Transcripts say what students SCORED. CheeseFork's public course feedback --
`course_ratings`, loaded by data-engineering -- says what they THOUGHT, on a
1-5 scale, and covers roughly half the catalog against our own handful of
courses. They are reported side by side rather than blended: a single score
would hide which one is talking, including when they disagree, and "hard but
worth it" is exactly the case a blended number destroys.

`michael-maltsev/technion-histograms` is NOT a third source. Every histogram
there is a PNG (720x405, ~2GB of pictures) with no numbers in it, so a grade
distribution would have to be recovered by image analysis; its `Staff.json`
files carry lecturer and TA names and emails, which is personal data with no
place in a bulk import.

Disclosure
----------
`MINIMUM_COHORT` exists because these are real students' grades. Below it, a
"course average" is close to naming an individual: with two rows, anyone who
knows one grade can derive the other. Small cohorts are dropped rather than
rounded, and no individual grade ever leaves this module.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from app.services.grade_evaluation import (
    counts_toward_average,
    is_passing_grade,
    parse_numeric_grade,
)

MINIMUM_COHORT = 5
"""Fewest transcripts a course needs before its statistics are published.

Five is the usual floor for aggregate disclosure. It is a privacy threshold
first and a statistical one second -- an average over two rows is both
identifying and meaningless.
"""


@dataclass(frozen=True)
class CourseOutcome:
    """What the transcripts we hold say about one course."""

    course_number: str
    sample_size: int
    mean_grade: float
    pass_rate: float

    @property
    def is_demanding(self) -> bool:
        """Fewer than nine in ten passed, on the registrar's own pass mark."""
        return self.pass_rate < 0.9

    def as_public_dict(self) -> dict[str, Any]:
        return {
            "courseNumber": self.course_number,
            "sampleSize": self.sample_size,
            "meanGrade": round(self.mean_grade, 1),
            "passRate": round(self.pass_rate, 3),
            "isDemanding": self.is_demanding,
        }


def _course_number_for(record: dict[str, Any]) -> str | None:
    number = record.get("courseNumber")
    if number:
        return str(number)
    imported = (record.get("metadata") or {}).get("importedCourseNumber")
    return str(imported) if imported else None


def build_course_outcomes(
    completed_course_records: list[dict[str, Any]],
    *,
    minimum_cohort: int = MINIMUM_COHORT,
) -> dict[str, CourseOutcome]:
    """Aggregate transcript rows into per-course outcomes, keyed by course number.

    Exemptions and pass/fail rows are excluded: they carry no score, so they
    would drag a mean toward a sentinel and tell you nothing about difficulty.
    Failed attempts ARE included -- they are most of the signal, and dropping
    them is what makes a hard course look easy.
    """
    grades: dict[str, list[float]] = defaultdict(list)
    passes: dict[str, int] = defaultdict(int)

    for record in completed_course_records:
        number = _course_number_for(record)
        if number is None or not counts_toward_average(record):
            continue
        grade = parse_numeric_grade(record.get("grade"))
        if grade is None:
            continue
        grades[number].append(grade)
        if is_passing_grade(record):
            passes[number] += 1

    outcomes: dict[str, CourseOutcome] = {}
    for number, values in grades.items():
        if len(values) < minimum_cohort:
            continue
        outcomes[number] = CourseOutcome(
            course_number=number,
            sample_size=len(values),
            mean_grade=sum(values) / len(values),
            pass_rate=passes[number] / len(values),
        )
    return outcomes


@dataclass(frozen=True)
class CourseSignal:
    """Everything we can say about a course, from both sources we have.

    Kept separate rather than blended into one score. They measure different
    things -- our transcripts say what students SCORED, CheeseFork's reviewers
    say what they THOUGHT -- and a single number would hide which one is
    driving it, including when they disagree.
    """

    course_number: str
    outcome: CourseOutcome | None = None
    rating: dict[str, Any] | None = None
    published: dict[str, Any] | None = None

    def as_public_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"courseNumber": self.course_number}
        if self.outcome is not None:
            payload["cohort"] = self.outcome.as_public_dict()
        if self.rating is not None:
            payload["reviews"] = {
                "responseCount": self.rating.get("responseCount"),
                "meanGeneralRank": self.rating.get("meanGeneralRank"),
                "meanDifficultyRank": self.rating.get("meanDifficultyRank"),
                "scaleMax": self.rating.get("scaleMax"),
                "source": self.rating.get("source"),
            }
        if self.published is not None:
            payload["published"] = {
                key: self.published.get(key)
                for key in (
                    "termCount",
                    "students",
                    "passed",
                    "failed",
                    "passRate",
                    "minGrade",
                    "maxGrade",
                    "averageGrade",
                    "medianOfTermMedians",
                    "source",
                )
            }
        return payload


def build_course_signals(
    course_numbers: list[str],
    *,
    outcomes: dict[str, CourseOutcome],
    ratings: dict[str, dict[str, Any]],
    published: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """One entry per course we can say anything about, in a stable order."""
    published = published or {}
    signals = []
    for number in sorted({str(n) for n in course_numbers if n}):
        outcome = outcomes.get(number)
        rating = ratings.get(number)
        stats = published.get(number)
        if outcome is None and rating is None and stats is None:
            continue
        signals.append(
            CourseSignal(
                course_number=number, outcome=outcome, rating=rating, published=stats
            ).as_public_dict()
        )
    return signals


def outcome_sort_key(
    course_number: str | None,
    outcomes: dict[str, CourseOutcome],
) -> tuple[int, float, float]:
    """Ordering key for breaking a tie between otherwise equal candidates.

    Deliberately a TIE-BREAK and not a primary sort. Ranking a plan by pass
    rate would steer students away from hard courses they need and toward easy
    ones they do not, which is a worse recommendation dressed up as a
    data-driven one. Courses with no statistics sort first so that thin
    coverage -- currently most of the catalog -- never pushes a course down.
    """
    outcome = outcomes.get(str(course_number)) if course_number else None
    if outcome is None:
        return (0, 0.0, 0.0)
    return (1, -outcome.pass_rate, -outcome.mean_grade)
