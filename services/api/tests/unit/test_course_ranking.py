"""Unit tests for ordering a shelf of candidate courses.

The objective is not "what would this student enjoy" but "what is the best use
of this semester's slot", which is a different question with a deadline
attached.
"""

from __future__ import annotations

import pytest

from app.planning.course_ranking import (
    PRIOR_RESPONSES,
    URGENCY_RUNWAY_CREDITS,
    diversify_by_faculty,
    prior_mean_rating,
    rank_candidates,
    shrunk_rating,
)


class TestShrunkRating:
    def test_a_mean_from_many_reviews_barely_moves(self) -> None:
        assert shrunk_rating(4.55, 69, prior_mean=3.5) == pytest.approx(4.44, abs=0.01)

    def test_a_mean_from_three_reviews_is_pulled_hard_toward_the_corpus(self) -> None:
        """36% of rated courses have five reviews or fewer, and every one of
        the ten highest raw means has six or fewer. Ranking on the raw mean
        selects for small samples, because that is where extreme means live.
        """
        assert shrunk_rating(5.0, 3, prior_mean=3.5) == pytest.approx(3.91, abs=0.01)

    def test_evidence_beats_a_lucky_perfect_score(self) -> None:
        well_reviewed = shrunk_rating(4.43, 136, prior_mean=3.5)
        barely_reviewed = shrunk_rating(5.0, 3, prior_mean=3.5)

        assert well_reviewed > barely_reviewed

    def test_no_reviews_is_exactly_the_prior(self) -> None:
        assert shrunk_rating(4.9, 0, prior_mean=3.5) == 3.5

    def test_the_prior_weight_is_the_median_response_count(self) -> None:
        """Chosen from the corpus rather than picked: below it small samples
        still dominate, above it everything compresses toward the mean and the
        ordering starts tracking review count instead of opinion."""
        assert PRIOR_RESPONSES == 8


class TestPriorMeanRating:
    def test_averages_the_corpus(self) -> None:
        ratings = {
            "1": {"meanGeneralRank": 3.0},
            "2": {"meanGeneralRank": 4.0},
        }

        assert prior_mean_rating(ratings) == 3.5

    def test_falls_back_when_there_is_too_little_to_average(self) -> None:
        """A prior estimated from two courses is not a corpus mean."""
        assert prior_mean_rating({"1": {"meanGeneralRank": 5.0}}) == 3.5

    def test_ignores_malformed_entries(self) -> None:
        ratings = {str(index): {"meanGeneralRank": 4.0} for index in range(30)}
        ratings["bad"] = {"meanGeneralRank": "excellent"}

        assert prior_mean_rating(ratings) == 4.0


class TestRankCandidates:
    def _candidates(self):
        return [
            {"courseNumber": "00940111", "credits": 3.0, "semestersOffered": [200, 201]},
            {"courseNumber": "00940222", "credits": 3.0, "semestersOffered": [200]},
        ]

    def test_a_scarce_course_outranks_a_better_reviewed_common_one_near_the_end(self) -> None:
        """With two semesters left, a course that will not run again for twelve
        months is the one to take now."""
        ranked = rank_candidates(
            self._candidates(),
            ratings={
                "00940111": {"meanGeneralRank": 4.5, "responseCount": 50},
                "00940222": {"meanGeneralRank": 3.0, "responseCount": 50},
            },
            credits_remaining_overall=20.0,
            credits_remaining_in_bucket=3.0,
        )

        assert [entry.course_number for entry in ranked] == ["00940222", "00940111"]
        assert "offered_once_a_year" in ranked[0].reasons

    def test_scarcity_does_not_override_quality_when_there_is_runway(self) -> None:
        """Three years out, taking a once-a-year course now rather than later
        is nearly free, so the better course should win."""
        ranked = rank_candidates(
            self._candidates(),
            ratings={
                "00940111": {"meanGeneralRank": 4.5, "responseCount": 50},
                "00940222": {"meanGeneralRank": 3.0, "responseCount": 50},
            },
            credits_remaining_overall=URGENCY_RUNWAY_CREDITS + 20,
            credits_remaining_in_bucket=3.0,
        )

        assert [entry.course_number for entry in ranked] == ["00940111", "00940222"]

    def test_a_course_that_closes_the_requirement_leads(self) -> None:
        ranked = rank_candidates(
            [
                {"courseNumber": "00940111", "credits": 2.0, "semestersOffered": [200, 201]},
                {"courseNumber": "00940222", "credits": 3.5, "semestersOffered": [200, 201]},
            ],
            ratings={
                "00940111": {"meanGeneralRank": 4.8, "responseCount": 50},
                "00940222": {"meanGeneralRank": 3.2, "responseCount": 50},
            },
            credits_remaining_overall=20.0,
            credits_remaining_in_bucket=3.5,
        )

        assert ranked[0].course_number == "00940222"
        assert "closes_requirement" in ranked[0].reasons

    def test_within_a_band_the_better_reviewed_course_leads(self) -> None:
        ranked = rank_candidates(
            [
                {"courseNumber": "00940111", "credits": 3.0, "semestersOffered": [200, 201]},
                {"courseNumber": "00940222", "credits": 3.0, "semestersOffered": [200, 201]},
            ],
            ratings={
                "00940111": {"meanGeneralRank": 3.0, "responseCount": 50},
                "00940222": {"meanGeneralRank": 4.5, "responseCount": 50},
            },
            credits_remaining_overall=20.0,
            credits_remaining_in_bucket=3.0,
        )

        assert [entry.course_number for entry in ranked] == ["00940222", "00940111"]

    def test_an_unreviewed_course_sits_at_the_corpus_mean_not_at_the_bottom(self) -> None:
        """A third of the catalog has no rating. Absence of an opinion is not a
        bad opinion, so it scores as average rather than as zero."""
        ranked = rank_candidates(
            [
                {"courseNumber": "00940111", "credits": 3.0, "semestersOffered": [200, 201]},
                {"courseNumber": "00940222", "credits": 3.0, "semestersOffered": [200, 201]},
            ],
            ratings={"00940111": {"meanGeneralRank": 2.0, "responseCount": 50}},
            credits_remaining_overall=20.0,
            credits_remaining_in_bucket=3.0,
        )

        assert ranked[0].course_number == "00940222"  # unrated beats a poorly rated one

    def test_the_order_is_stable_across_calls(self) -> None:
        candidates = [
            {"courseNumber": number, "credits": 3.0, "semestersOffered": [200, 201]}
            for number in ("00940333", "00940111", "00940222")
        ]

        first = [entry.course_number for entry in rank_candidates(
            candidates, ratings={}, credits_remaining_overall=20.0, credits_remaining_in_bucket=3.0
        )]
        second = [entry.course_number for entry in rank_candidates(
            list(reversed(candidates)), ratings={},
            credits_remaining_overall=20.0, credits_remaining_in_bucket=3.0,
        )]

        assert first == second

    def test_a_well_reviewed_course_says_so(self) -> None:
        ranked = rank_candidates(
            [{"courseNumber": "00940111", "credits": 3.0, "semestersOffered": [200, 201]}],
            ratings={"00940111": {"meanGeneralRank": 4.5, "responseCount": 69}},
            credits_remaining_overall=20.0,
            credits_remaining_in_bucket=3.0,
        )

        assert "well_reviewed" in ranked[0].reasons


class TestDiversifyByFaculty:
    def _entry(self, number, faculty):
        return {"courseNumber": number, "faculty": faculty}

    def test_a_row_does_not_become_three_departments(self) -> None:
        """Six of the eight best-scoring courses in the catalog come from two
        faculties. A row of 24 that is really 3 departments is a worse row."""
        courses = [self._entry(f"0324{i:04d}", "Civil") for i in range(6)]
        courses += [self._entry(f"0194{i:04d}", "Physics") for i in range(6)]

        ordered = diversify_by_faculty(courses, limit=6, per_faculty=2)

        faculties = [course["faculty"] for course in ordered]
        assert faculties.count("Civil") == 2
        assert faculties.count("Physics") == 2
        assert len(ordered) == 4  # nothing else qualifies to fill the row

    def test_the_best_of_each_faculty_is_the_one_kept(self) -> None:
        courses = [
            self._entry("00324001", "Civil"),
            self._entry("00324002", "Civil"),
            self._entry("00194001", "Physics"),
        ]

        ordered = diversify_by_faculty(courses, limit=3, per_faculty=1)

        assert [c["courseNumber"] for c in ordered] == ["00324001", "00194001"]

    def test_courses_without_a_faculty_are_not_pooled_together(self) -> None:
        """Treating "unknown" as one department would cap them collectively."""
        courses = [self._entry(f"0032400{i}", None) for i in range(4)]

        assert len(diversify_by_faculty(courses, limit=4, per_faculty=1)) == 4

    def test_an_unlimited_row_is_returned_untouched(self) -> None:
        courses = [self._entry("00324001", "Civil"), self._entry("00324002", "Civil")]

        assert diversify_by_faculty(courses, limit=10, per_faculty=None) == courses


class TestPersonalisation:
    def _pair(self):
        return [
            {"courseNumber": "00940111", "credits": 3.0, "semestersOffered": [200, 201],
             "faculty": "Mathematics"},
            {"courseNumber": "00940222", "credits": 3.0, "semestersOffered": [200, 201],
             "faculty": "Humanities"},
        ]

    def test_a_faculty_the_student_keeps_choosing_leads_its_band(self) -> None:
        """The one part of the order that differs between two students looking
        at the same row."""
        ranked = rank_candidates(
            self._pair(),
            ratings={
                "00940111": {"meanGeneralRank": 4.5, "responseCount": 50},
                "00940222": {"meanGeneralRank": 3.0, "responseCount": 50},
            },
            credits_remaining_overall=20.0,
            credits_remaining_in_bucket=3.0,
            faculty_affinity={"Humanities": 0.6, "Mathematics": 0.1},
        )

        assert ranked[0].course_number == "00940222"
        assert "matches_your_electives" in ranked[0].reasons

    def test_without_a_history_the_order_falls_back_to_the_shared_one(self) -> None:
        ranked = rank_candidates(
            self._pair(),
            ratings={
                "00940111": {"meanGeneralRank": 4.5, "responseCount": 50},
                "00940222": {"meanGeneralRank": 3.0, "responseCount": 50},
            },
            credits_remaining_overall=20.0,
            credits_remaining_in_bucket=3.0,
            faculty_affinity={},
        )

        assert ranked[0].course_number == "00940111"

    def test_a_single_curiosity_is_not_a_pattern(self) -> None:
        """One course out of ten in a faculty does not make it theirs."""
        ranked = rank_candidates(
            self._pair(),
            ratings={},
            credits_remaining_overall=20.0,
            credits_remaining_in_bucket=3.0,
            faculty_affinity={"Humanities": 0.1},
        )

        assert all("matches_your_electives" not in entry.reasons for entry in ranked)

    def test_affinity_never_outranks_a_structural_cost(self) -> None:
        """Interest orders within a band; it does not beat a course that closes
        the requirement or will not run again for a year."""
        courses = [
            {"courseNumber": "00940111", "credits": 3.5, "semestersOffered": [200],
             "faculty": "Mathematics"},
            {"courseNumber": "00940222", "credits": 1.0, "semestersOffered": [200, 201],
             "faculty": "Humanities"},
        ]

        ranked = rank_candidates(
            courses,
            ratings={},
            credits_remaining_overall=20.0,
            credits_remaining_in_bucket=3.5,
            faculty_affinity={"Humanities": 0.9},
        )

        assert ranked[0].course_number == "00940111"
