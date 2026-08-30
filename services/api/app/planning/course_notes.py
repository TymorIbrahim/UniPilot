"""Operational facts about a course that live only in its free-text notes.

1,006 catalog courses carry a `notes` string, and it is the only place some
practical facts are recorded. The one worth acting on is manual registration:

    "הקורס הינו ברישום ידני באישור המרצה. יש לשלוח מייל בקשה לרישום
     בצירוף גליון ציונים למרצה הקורס"

-- the student cannot enrol through the normal system at all; they must email
the lecturer with their transcript and be accepted. Planning such a course
without knowing that is how a semester plan quietly fails to become a
timetable.

Matched rather than parsed
--------------------------
`רישום ידני` ("manual registration") is a fixed phrase and every occurrence
inspected states exactly this. Nothing else in the notes is extracted: the rest
is prose about shared lectures, room changes and lecturer names, where a
keyword would guess more than it knows. The flag is additive -- it never hides
or reorders a course, only says something true about enrolling in it.
"""

from __future__ import annotations

import re

MANUAL_REGISTRATION_PATTERN = re.compile(r"רישום\s+ידני|ידני\s+באישור|רישום\s+הינו\s+ידני")
"""Phrasings of "manual registration" seen in the catalog."""


def requires_manual_registration(notes: str | None) -> bool:
    """Whether the notes say the student cannot enrol through the normal system."""
    if not notes:
        return False
    return bool(MANUAL_REGISTRATION_PATTERN.search(str(notes)))
