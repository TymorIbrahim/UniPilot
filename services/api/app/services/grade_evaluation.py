"""Technion numeric grade evaluation (0–100 scale; minimum pass grade is 55)."""

from __future__ import annotations

from typing import Any

PASSING_GRADE_THRESHOLD = 55


def parse_numeric_grade(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            numeric = float(stripped)
        except ValueError:
            return None
    else:
        return None

    if numeric < 0 or numeric > 100:
        return None
    return numeric


def resolve_record_numeric_grade(record: dict[str, Any]) -> float | None:
    """Prefer the official numeric grade; fall back to gradePoints when grade is absent."""
    grade = parse_numeric_grade(record.get("grade"))
    if grade is not None:
        return grade
    return parse_numeric_grade(record.get("gradePoints"))


def is_non_numeric_outcome(record: dict[str, Any] | Any) -> bool:
    """True when the registrar recorded פטור / עובר rather than a score.

    The transcript parser has no way to put "exempt" in a `grade: float` field,
    so it writes a sentinel (0 for an exemption without points) and records what
    it really saw in the row's warnings; the import turns those into
    `metadata.exemption` / `metadata.passGrade`. Anything that reads the number
    alone sees 0 and calls a passed course a failure -- which is exactly what
    happened: a student with one genuine fail was told they had three, because
    two exemption rows scored 0.
    """
    if not isinstance(record, dict):
        return False
    metadata = record.get("metadata") or {}
    if not isinstance(metadata, dict):
        return False
    return bool(metadata.get("exemption")) or bool(metadata.get("passGrade"))


def counts_toward_average(record: dict[str, Any] | Any) -> bool:
    """True when this row's grade belongs in the registrar's weighted average.

    Exemptions and pass/fail rows carry credits but no score, and the Technion
    leaves them out of the average while still counting their credits. Verified
    against an official transcript: including them gives 74.8 where the sheet
    itself states 74.1; excluding them gives 74.06.
    """
    if not isinstance(record, dict):
        return False
    if is_non_numeric_outcome(record):
        return False
    return parse_numeric_grade(record.get("grade")) is not None


def is_passing_numeric_grade(numeric_grade: float) -> bool:
    return numeric_grade >= PASSING_GRADE_THRESHOLD


def is_passing_grade(record: dict[str, Any] | Any, grade_points: Any = None) -> bool:
    """Return True when the student passed (score at or above the minimum pass grade)."""
    if isinstance(record, dict):
        if is_non_numeric_outcome(record):
            return True
        grade = parse_numeric_grade(record.get("grade"))
        if grade is not None:
            return is_passing_numeric_grade(grade)
        points = parse_numeric_grade(record.get("gradePoints"))
        if points is not None:
            return is_passing_numeric_grade(points)
        return False

    numeric = parse_numeric_grade(grade_points)
    if numeric is None:
        numeric = parse_numeric_grade(record)

    if numeric is None:
        return False
    return is_passing_numeric_grade(numeric)
