"""Tests for the CheeseFork course-feedback reader."""

from __future__ import annotations

import pytest

from app.sources.cheesefork_feedback import (
    MINIMUM_RESPONSES,
    CourseRating,
    document_url,
    parse_feedback_document,
)


def _post(general=None, difficulty=None, **extra):
    fields = {}
    if general is not None:
        fields["generalRank"] = {"integerValue": str(general)}
    if difficulty is not None:
        fields["difficultyRank"] = {"integerValue": str(difficulty)}
    fields.update(extra)
    return {"mapValue": {"fields": fields}}


def _document(posts):
    return {"fields": {"posts": {"arrayValue": {"values": posts}}}}


def test_averages_both_ranks_over_the_posts() -> None:
    document = _document(
        [_post(general=2, difficulty=4), _post(general=4, difficulty=2), _post(general=3, difficulty=3)]
    )

    rating = parse_feedback_document(document, course_number="00940224")

    assert rating == CourseRating(
        course_number="00940224", response_count=3, mean_general=3.0, mean_difficulty=3.0
    )


def test_integer_ranks_arrive_as_strings_and_must_be_converted() -> None:
    """Firestore REST tags every value and sends integers as text.

    Read without conversion they average as nonsense rather than failing.
    """
    document = _document([_post(general=5, difficulty=1)] * 3)

    rating = parse_feedback_document(document, course_number="00940224")

    assert rating is not None
    assert isinstance(rating.mean_general, float)
    assert rating.mean_general == 5.0
    assert rating.mean_difficulty == 1.0


def test_a_post_missing_one_rank_still_counts_for_the_other() -> None:
    """Reviewers routinely rate difficulty and skip the general score."""
    document = _document(
        [_post(general=4, difficulty=2), _post(difficulty=4), _post(general=2, difficulty=3)]
    )

    rating = parse_feedback_document(document, course_number="00940224")

    assert rating is not None
    assert rating.response_count == 3
    assert rating.mean_general == 3.0  # only the two that answered it
    assert rating.mean_difficulty == 3.0


def test_too_few_responses_is_not_reported() -> None:
    document = _document([_post(general=5, difficulty=1)] * (MINIMUM_RESPONSES - 1))

    assert parse_feedback_document(document, course_number="00940224") is None


def test_a_course_with_no_posts_is_not_reported() -> None:
    assert parse_feedback_document(_document([]), course_number="00940224") is None
    assert parse_feedback_document({}, course_number="00940224") is None


def test_a_document_with_only_one_kind_of_rank_is_not_reported() -> None:
    """Reporting a difficulty with no quality score (or the reverse) invites
    reading the one that is present as the one that is missing."""
    document = _document([_post(difficulty=4)] * 4)

    assert parse_feedback_document(document, course_number="00940224") is None


@pytest.mark.parametrize("rank", [0, 6, -1, 99])
def test_a_rank_outside_the_scale_is_discarded(rank) -> None:
    document = _document([_post(general=rank, difficulty=rank)] * 4)

    assert parse_feedback_document(document, course_number="00940224") is None


def test_non_numeric_and_null_ranks_are_discarded() -> None:
    posts = [
        {"mapValue": {"fields": {"generalRank": {"stringValue": "good"}}}},
        {"mapValue": {"fields": {"difficultyRank": {"nullValue": None}}}},
        {"mapValue": {"fields": {"generalRank": {"integerValue": "not-a-number"}}}},
        {"mapValue": {"fields": {"difficultyRank": {"doubleValue": "nope"}}}},
        {"mapValue": {"fields": {}}},
        {"mapValue": {"fields": "not-a-mapping"}},
    ]

    assert parse_feedback_document(_document(posts), course_number="00940224") is None


def test_double_ranks_are_accepted() -> None:
    posts = [{"mapValue": {"fields": {
        "generalRank": {"doubleValue": "4.0"},
        "difficultyRank": {"doubleValue": "2.0"},
    }}}] * 3

    rating = parse_feedback_document(_document(posts), course_number="00940224")

    assert rating is not None
    assert rating.mean_general == 4.0


def test_public_dict_keeps_the_numbers_and_drops_the_prose() -> None:
    """`text` is other students' writing; the ranks are the signal."""
    document = _document(
        [_post(general=4, difficulty=2, text={"stringValue": "a long review"})] * 3
    )

    payload = parse_feedback_document(document, course_number="00940224").as_public_dict()

    assert payload == {
        "courseNumber": "00940224",
        "responseCount": 3,
        "meanGeneralRank": 4.0,
        "meanDifficultyRank": 2.0,
        "scaleMin": 1,
        "scaleMax": 5,
    }
    assert "text" not in payload
    assert "author" not in payload


def test_document_url_targets_the_public_collection() -> None:
    url = document_url("cheesefork-de9af", "00940224", "KEY")

    assert "/documents/courseFeedback/00940224" in url
    assert url.endswith("?key=KEY")
