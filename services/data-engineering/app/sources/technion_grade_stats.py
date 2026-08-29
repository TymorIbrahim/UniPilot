"""Read published Technion grade statistics into per-course aggregates.

Where these come from
---------------------
`michael-maltsev/technion-histograms` publishes one `index.json` per course on
its `gh-pages` branch, alongside the histogram images. The JSON is the part
worth having: for every term and every sitting it carries the numbers printed
under the histogram --

    students, passFail ("143/24"), passPercent, min, max, average, median

-- which is a real grade distribution summary, not a picture of one. 2,750
courses have such a file.

Which sitting counts
--------------------
A term holds several sections. `Exam_A` / `Exam_B` are the exam alone;
`Final_A` / `Final_B` are the course grade after homework and projects, per
sitting; `Finals` is the term's overall final distribution. `Finals` is what a
student means by "the grade for this course", so it is preferred, falling back
to `Final_A` when a term has no combined figure. Reading `Exam_A` instead
reports a systematically harsher course than students actually experience --
in one measured case 70.5 against 77.7 for the same term.

Every value arrives as a STRING ("167", "70.545"), so anything that skips
conversion sorts and averages them as text.

Combining terms
---------------
A course's terms are pooled weighted by cohort size, because a 15-student
summer sitting should not move the average as much as a 300-student winter one.
Min and max are taken across all terms; the median is averaged (a true pooled
median needs the underlying grades, which are not published) and is labelled as
such.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

PREFERRED_SECTIONS = ("Finals", "Final_A", "Final_B")
"""Course-grade sections, best first. Exam-only sections are deliberately absent."""

_PASS_FAIL = re.compile(r"^\s*(\d+)\s*/\s*(\d+)\s*$")


@dataclass(frozen=True)
class TermGradeStats:
    """One term's published distribution for a course."""

    term: str
    students: int
    passed: int
    failed: int
    minimum: float
    maximum: float
    average: float
    median: float

    @property
    def pass_rate(self) -> float:
        return self.passed / self.students if self.students else 0.0


@dataclass(frozen=True)
class CourseGradeStats:
    """A course's published distribution, pooled across the terms we have."""

    course_number: str
    term_count: int
    students: int
    passed: int
    failed: int
    minimum: float
    maximum: float
    average: float
    median_of_term_medians: float

    @property
    def pass_rate(self) -> float:
        return self.passed / self.students if self.students else 0.0

    def as_public_dict(self) -> dict[str, Any]:
        return {
            "courseNumber": self.course_number,
            "termCount": self.term_count,
            "students": self.students,
            "passed": self.passed,
            "failed": self.failed,
            "passRate": round(self.pass_rate, 3),
            "minGrade": self.minimum,
            "maxGrade": self.maximum,
            "averageGrade": round(self.average, 2),
            # Named for what it is: the mean of each term's median, because the
            # underlying grades needed for a true pooled median are not published.
            "medianOfTermMedians": round(self.median_of_term_medians, 2),
            "source": "technion-histograms",
        }


def _number(raw: Any) -> float | None:
    if raw is None or isinstance(raw, bool):
        return None
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return None


def _pass_fail(raw: Any) -> tuple[int, int] | None:
    match = _PASS_FAIL.match(str(raw or ""))
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def parse_term_section(term: str, section: dict[str, Any]) -> TermGradeStats | None:
    """One `Finals`/`Final_A` block, or None when it is not fully populated.

    A partial row is dropped rather than defaulted: a zero minimum or an absent
    cohort size would pass straight through the pooling and quietly bias every
    number computed from it.
    """
    if not isinstance(section, dict):
        return None
    counts = _pass_fail(section.get("passFail"))
    students = _number(section.get("students"))
    average = _number(section.get("average"))
    median = _number(section.get("median"))
    minimum = _number(section.get("min"))
    maximum = _number(section.get("max"))
    if counts is None or None in (students, average, median, minimum, maximum):
        return None
    if students <= 0:
        return None

    passed, failed = counts
    return TermGradeStats(
        term=term,
        students=int(students),
        passed=passed,
        failed=failed,
        minimum=minimum,
        maximum=maximum,
        average=average,
        median=median,
    )


def select_course_section(term_block: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    """The course-grade section for a term, preferring the combined figure."""
    if not isinstance(term_block, dict):
        return None
    for name in PREFERRED_SECTIONS:
        section = term_block.get(name)
        if isinstance(section, dict):
            return name, section
    return None


def parse_course_index(
    document: dict[str, Any],
    *,
    course_number: str,
) -> CourseGradeStats | None:
    """Pool a course's `index.json` into one distribution summary."""
    if not isinstance(document, dict):
        return None

    terms: list[TermGradeStats] = []
    for term, block in document.items():
        selected = select_course_section(block)
        if selected is None:
            continue
        stats = parse_term_section(term, selected[1])
        if stats is not None:
            terms.append(stats)

    if not terms:
        return None

    students = sum(t.students for t in terms)
    weighted_average = sum(t.average * t.students for t in terms) / students
    return CourseGradeStats(
        course_number=course_number,
        term_count=len(terms),
        students=students,
        passed=sum(t.passed for t in terms),
        failed=sum(t.failed for t in terms),
        minimum=min(t.minimum for t in terms),
        maximum=max(t.maximum for t in terms),
        average=weighted_average,
        median_of_term_medians=sum(t.median for t in terms) / len(terms),
    )


def index_url(course_number: str) -> str:
    """Raw URL for one course's published statistics."""
    return (
        "https://raw.githubusercontent.com/michael-maltsev/technion-histograms"
        f"/gh-pages/{course_number}/index.json"
    )
