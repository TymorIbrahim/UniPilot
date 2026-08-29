"""Keep courses meant for another degree level off a student's rows.

The gap
-------
`studyFramework` is populated on all 2,613 catalog courses and takes four
values: undergraduate studies, shared courses, graduate degrees, and
pre-academic. Nothing in the planner consulted it, so 197 graduate courses
offered in one term sat in an undergraduate's candidate pool -- and 108 of them
state no prerequisites at all, which means eligibility filtering does not stop
them either. Graduate seminars stayed off the rows only because the open rows
cap at 24 and unrated courses lose to rated ones, which is luck rather than a
rule.

The student's level comes from `programType` on their profile (BSc, MSc, PhD),
which is set on every real profile. Degree programs carry no level of their own.

Graduate students keep undergraduate courses
--------------------------------------------
The restriction is not symmetric. A BSc student has no business being offered a
graduate seminar, but MSc and PhD students routinely take undergraduate courses
as completion requirements, so those stay on their rows.

Fail open, always
-----------------
An unrecognised `programType`, or a course whose framework is missing, is not
filtered. Hiding a course the student may well be entitled to, on the strength
of a value we do not recognise, is a worse error than showing one too many --
the student can see what a course is; they cannot see what we silently removed.
"""

from __future__ import annotations

UNDERGRADUATE = "לימודי הסמכה"
SHARED = "מקצוע משותף"
GRADUATE = "תארים מתקדמים"
PRE_ACADEMIC = "קדם אקדמי/תיכוני"

ALLOWED_FRAMEWORKS: dict[str, frozenset[str]] = {
    "BSC": frozenset({UNDERGRADUATE, SHARED}),
    "MSC": frozenset({GRADUATE, SHARED, UNDERGRADUATE}),
    "PHD": frozenset({GRADUATE, SHARED, UNDERGRADUATE}),
}
"""Course frameworks each degree level may be offered.

Pre-academic courses are absent everywhere: they are remedial preparation for
university rather than part of any degree, so they count toward nothing.
"""


def allowed_frameworks(program_type: str | None) -> frozenset[str] | None:
    """Frameworks this student may be shown, or None to apply no restriction."""
    if not program_type:
        return None
    return ALLOWED_FRAMEWORKS.get(str(program_type).strip().upper())


def is_appropriate_level(
    study_framework: str | None,
    *,
    allowed: frozenset[str] | None,
) -> bool:
    """Whether a course belongs on this student's rows.

    True whenever there is no restriction to apply or the course does not say
    what it is -- see the module docstring on why this fails open.
    """
    if allowed is None:
        return True
    framework = str(study_framework or "").strip()
    if not framework:
        return True
    return framework in allowed
