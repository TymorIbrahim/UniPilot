"""Read CheeseFork's public course feedback into per-course rating aggregates.

What this reads
---------------
`courseFeedback/<courseNumber>` in the CheeseFork Firestore project, over the
REST API with the same public web key the site itself ships. The collection is
world-readable -- no sign-in, no token -- which is what makes it usable here:
this is the same data any visitor sees on cheesefork.cf, fetched the same way.

Each post carries `difficultyRank` and `generalRank` on a 1-5 scale, plus a
semester, a timestamp, and free text.

Numbers only, deliberately
--------------------------
`text` is other students' written reviews. It is the part of the payload with
no recommendation value that we do not already get from the ranks, and
re-hosting someone's writing inside UniPilot brings attribution and moderation
along with it for nothing in return. The aggregates keep the two ranks and the
sample size and drop the prose, the author field, and the timestamps.

Ranks are 1-5 and mean opposite things
--------------------------------------
`generalRank` is "was this course good" -- higher is better. `difficultyRank`
is "how hard was it" -- higher is HARDER. Averaging them together, or reading
one as the other, produces a recommender that confidently prefers the courses
students found worst.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

RATING_SCALE_MIN = 1
RATING_SCALE_MAX = 5

MINIMUM_RESPONSES = 3
"""Fewest posts before a course's averages are worth reporting.

Lower than the transcript threshold because these are opinions volunteered
publicly, not grades: the concern is that one review is noise, not that it
identifies anybody.
"""


@dataclass(frozen=True)
class CourseRating:
    """What CheeseFork's reviewers said about one course, in aggregate."""

    course_number: str
    response_count: int
    mean_general: float
    mean_difficulty: float

    def as_public_dict(self) -> dict[str, Any]:
        return {
            "courseNumber": self.course_number,
            "responseCount": self.response_count,
            "meanGeneralRank": round(self.mean_general, 2),
            "meanDifficultyRank": round(self.mean_difficulty, 2),
            "scaleMin": RATING_SCALE_MIN,
            "scaleMax": RATING_SCALE_MAX,
        }


def _scalar(field: dict[str, Any] | None) -> Any:
    """Unwrap one Firestore REST typed value.

    Every value arrives tagged -- `{"integerValue": "4"}`, `{"stringValue": ...}`
    -- and integers arrive as STRINGS, so reading them without conversion
    silently yields text that compares and averages as nonsense.
    """
    if not isinstance(field, dict) or not field:
        return None
    key, value = next(iter(field.items()))
    if key == "integerValue":
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    if key == "doubleValue":
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    if key == "nullValue":
        return None
    return value


def _rank(field: dict[str, Any] | None) -> float | None:
    """A 1-5 rank, or None when it is absent or out of range."""
    value = _scalar(field)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    if not RATING_SCALE_MIN <= value <= RATING_SCALE_MAX:
        return None
    return float(value)


def parse_feedback_document(
    document: dict[str, Any],
    *,
    course_number: str,
    minimum_responses: int = MINIMUM_RESPONSES,
) -> CourseRating | None:
    """Aggregate one `courseFeedback` document, or None when it says too little.

    A post missing a rank is counted only for the rank it does carry: reviewers
    routinely rate difficulty and skip the general score, and discarding the
    whole post would throw away the half they did answer.
    """
    posts = (
        document.get("fields", {})
        .get("posts", {})
        .get("arrayValue", {})
        .get("values", [])
    )

    general: list[float] = []
    difficulty: list[float] = []
    for post in posts:
        fields = post.get("mapValue", {}).get("fields", {})
        if not isinstance(fields, dict):
            continue
        if (value := _rank(fields.get("generalRank"))) is not None:
            general.append(value)
        if (value := _rank(fields.get("difficultyRank"))) is not None:
            difficulty.append(value)

    responses = max(len(general), len(difficulty))
    if responses < minimum_responses or not general or not difficulty:
        return None

    return CourseRating(
        course_number=course_number,
        response_count=responses,
        mean_general=sum(general) / len(general),
        mean_difficulty=sum(difficulty) / len(difficulty),
    )


def document_url(project: str, course_number: str, api_key: str) -> str:
    """REST URL for one course's feedback document."""
    return (
        f"https://firestore.googleapis.com/v1/projects/{project}"
        f"/databases/(default)/documents/courseFeedback/{course_number}"
        f"?key={api_key}"
    )
