"""Unit tests for grouping candidate courses by the requirement they advance.

`build_candidate_pools` flattens every candidate into one mandatory list and
one elective list, which is what the auto-planner needs and exactly what a
browsable planner cannot use: the bucket a course would advance -- the reason
to show it at all -- is computed upstream and then discarded.
"""

from __future__ import annotations

from app.planning.course_shelves import build_course_shelves, rank_choice_courses


def _bucket(group_id, title, *, status="in_progress", remaining=(), credits_remaining=3.0,
            requirement_type="elective", is_mandatory=False):
    return {
        "requirementGroupId": group_id,
        "title": title,
        "status": status,
        "requirementType": requirement_type,
        "isMandatory": is_mandatory,
        "creditsRemaining": credits_remaining,
        "remainingCourses": [{"courseNumber": number} for number in remaining],
    }


def _pool(group_id, bucket_id, title, *courses):
    return {
        "requirementGroupId": group_id,
        "linkedCreditBucketId": bucket_id,
        "title": title,
        "courseReferences": [{"courseNumber": number} for number in courses],
    }


class TestShelfSelection:
    def test_a_satisfied_bucket_produces_no_shelf(self) -> None:
        """Physical Education is done; a row for it is only clutter."""
        shelves = build_course_shelves(
            requirement_progress=[
                _bucket("p:physical-education", "Physical Education", status="satisfied")
            ],
            pool_documents=[],
        )

        assert shelves == []

    def test_named_remaining_courses_become_a_mandatory_shelf(self) -> None:
        shelves = build_course_shelves(
            requirement_progress=[
                _bucket(
                    "p:core-mandatory",
                    "Required courses",
                    remaining=("00940704", "00940412"),
                    requirement_type="core",
                    is_mandatory=True,
                )
            ],
            pool_documents=[],
        )

        assert len(shelves) == 1
        assert shelves[0].kind == "mandatory"
        assert shelves[0].is_choice is False
        assert shelves[0].course_numbers == ("00940704", "00940412")

    def test_an_elective_bucket_lists_options_not_obligations(self) -> None:
        """`isMandatory` is true on "Faculty electives" because the BUCKET is
        required -- 35.5 credits of it -- not because its 10 named courses are.
        Reading that flag as an obligation tells the student to take all ten.
        """
        shelves = build_course_shelves(
            requirement_progress=[
                _bucket(
                    "p:elective-faculty",
                    "Faculty electives",
                    remaining=("00970209", "00960212"),
                    requirement_type="elective",
                    is_mandatory=True,
                )
            ],
            pool_documents=[],
        )

        assert shelves[0].kind == "pool"
        assert shelves[0].is_choice is True

    def test_a_linked_pool_becomes_its_own_choice_shelf(self) -> None:
        shelves = build_course_shelves(
            requirement_progress=[_bucket("p:elective-faculty", "Faculty electives")],
            pool_documents=[
                _pool("p:is-focus-chain-ml", "p:elective-faculty", "ML chain", "00970209", "00960212")
            ],
        )

        assert len(shelves) == 1
        assert shelves[0].kind == "pool"
        assert shelves[0].is_choice is True
        assert shelves[0].title == "ML chain"
        assert shelves[0].requirement_group_id == "p:elective-faculty"
        assert shelves[0].course_numbers == ("00970209", "00960212")

    def test_one_bucket_with_several_pools_yields_a_shelf_each(self) -> None:
        """`elective-faculty` links four pools -- three thematic focus chains
        and a catch-all. They are alternative ways to spend the same credits,
        which is precisely a row each rather than one merged list."""
        shelves = build_course_shelves(
            requirement_progress=[_bucket("p:elective-faculty", "Faculty electives")],
            pool_documents=[
                _pool("p:chain-ml", "p:elective-faculty", "ML chain", "00970209"),
                _pool("p:chain-game-theory", "p:elective-faculty", "Game theory", "00960212"),
                _pool("p:additional", "p:elective-faculty", "Additional electives", "00940412"),
            ],
        )

        assert [shelf.title for shelf in shelves] == [
            "Additional electives",
            "Game theory",
            "ML chain",
        ]
        assert {shelf.requirement_group_id for shelf in shelves} == {"p:elective-faculty"}

    def test_a_bucket_can_carry_both_required_courses_and_a_choice_pool(self) -> None:
        """`core-mandatory` has named courses AND a science-supplement pool.
        Merging them would present a free choice as an obligation."""
        shelves = build_course_shelves(
            requirement_progress=[
                _bucket(
                    "p:core-mandatory",
                    "Required courses",
                    remaining=("00940704",),
                    requirement_type="core",
                    is_mandatory=True,
                )
            ],
            pool_documents=[
                _pool("p:science-supplement", "p:core-mandatory", "Science supplement", "00940412")
            ],
        )

        assert [(shelf.kind, shelf.is_choice) for shelf in shelves] == [
            ("mandatory", False),
            ("pool", True),
        ]

    def test_a_bucket_with_no_enumerable_courses_is_an_open_shelf(self) -> None:
        """Free electives and enrichment mean "anything counts". Their pools
        are empty by design, so the candidates are the term's offerings and
        the shelf says so rather than rendering blank."""
        shelves = build_course_shelves(
            requirement_progress=[
                _bucket("p:free-elective", "Free electives", credits_remaining=2.0)
            ],
            pool_documents=[_pool("p:free-elective-pool", "p:free-elective", "Free pool")],
        )

        assert len(shelves) == 1
        assert shelves[0].kind == "open"
        assert shelves[0].is_choice is True
        assert shelves[0].course_numbers == ()

    def test_a_pool_linked_to_a_satisfied_bucket_is_not_shown(self) -> None:
        shelves = build_course_shelves(
            requirement_progress=[
                _bucket("p:physical-education", "PE", status="satisfied")
            ],
            pool_documents=[_pool("p:pe-pool", "p:physical-education", "PE pool", "00390101")],
        )

        assert shelves == []

    def test_a_pool_linked_to_no_known_bucket_is_ignored(self) -> None:
        """Its credits would land somewhere we cannot name, so we do not claim
        the course counts for anything."""
        shelves = build_course_shelves(
            requirement_progress=[_bucket("p:elective-faculty", "Faculty electives")],
            pool_documents=[_pool("p:orphan", "p:no-such-bucket", "Orphan", "00940412")],
        )

        assert [shelf.shelf_id for shelf in shelves] == ["p:elective-faculty"]
        assert shelves[0].kind == "open"  # the bucket still needs credits
        assert "00940412" not in shelves[0].course_numbers


class TestCompletedCourses:
    def test_courses_already_passed_drop_out_of_a_shelf(self) -> None:
        shelves = build_course_shelves(
            requirement_progress=[_bucket("p:elective-faculty", "Faculty electives")],
            pool_documents=[
                _pool("p:chain", "p:elective-faculty", "Chain", "00970209", "00960212")
            ],
            completed_course_numbers={"00970209"},
        )

        assert shelves[0].course_numbers == ("00960212",)

    def test_a_pool_the_student_has_exhausted_yields_an_open_shelf(self) -> None:
        """The requirement still needs credits, so the row must stay -- but it
        can no longer be filled from this pool."""
        shelves = build_course_shelves(
            requirement_progress=[_bucket("p:elective-faculty", "Faculty electives")],
            pool_documents=[_pool("p:chain", "p:elective-faculty", "Chain", "00970209")],
            completed_course_numbers={"00970209"},
        )

        assert [shelf.kind for shelf in shelves] == ["open"]
        assert shelves[0].credits_remaining == 3.0


class TestShelfMetadata:
    def test_a_shelf_carries_what_the_row_header_needs(self) -> None:
        shelves = build_course_shelves(
            requirement_progress=[
                _bucket("p:elective-faculty", "Faculty electives", credits_remaining=3.5)
            ],
            pool_documents=[_pool("p:chain", "p:elective-faculty", "ML chain", "00970209")],
        )

        shelf = shelves[0]
        assert shelf.shelf_id == "p:chain"
        assert shelf.requirement_title == "Faculty electives"
        assert shelf.credits_remaining == 3.5

    def test_course_numbers_are_normalised(self) -> None:
        """A legacy 6-digit reference must match the 8-digit catalog."""
        shelves = build_course_shelves(
            requirement_progress=[_bucket("p:elective-faculty", "Faculty electives")],
            pool_documents=[_pool("p:chain", "p:elective-faculty", "Chain", "970209")],
        )

        assert shelves[0].course_numbers == ("00970209",)

    def test_duplicate_references_appear_once(self) -> None:
        shelves = build_course_shelves(
            requirement_progress=[_bucket("p:elective-faculty", "Faculty electives")],
            pool_documents=[
                _pool("p:chain", "p:elective-faculty", "Chain", "00970209", "00970209")
            ],
        )

        assert shelves[0].course_numbers == ("00970209",)


class TestRankChoiceCourses:
    def test_better_rated_courses_come_first(self) -> None:
        ranked = rank_choice_courses(
            ["00940412", "00940423"],
            ratings={
                "00940412": {"meanGeneralRank": 2.86},
                "00940423": {"meanGeneralRank": 3.64},
            },
        )

        assert ranked == ("00940423", "00940412")

    def test_pass_rate_does_not_order_a_menu(self) -> None:
        """A 98% pass rate means the course is easy, not that it is good.
        Ordering a free choice by easiness is a worse recommendation dressed up
        as a data-driven one."""
        ranked = rank_choice_courses(
            ["00940820", "00940591"],
            ratings={
                # 00940820 passes 98% of its cohort but reviewers rate it 2.9;
                # 00940591 passes 92% and reviewers rate it 3.98.
                "00940820": {"meanGeneralRank": 2.9, "passRate": 0.98},
                "00940591": {"meanGeneralRank": 3.98, "passRate": 0.92},
            },
        )

        assert ranked[0] == "00940591"

    def test_unrated_courses_trail_the_rated_ones_in_catalog_order(self) -> None:
        """Absence of an opinion is not a bad opinion -- a third of the catalog
        has no rating, and burying those courses would be a claim we cannot
        support."""
        ranked = rank_choice_courses(
            ["00940999", "00940412", "00940111"],
            ratings={"00940412": {"meanGeneralRank": 1.5}},
        )

        assert ranked == ("00940412", "00940111", "00940999")

    def test_a_malformed_rating_is_treated_as_no_rating(self) -> None:
        ranked = rank_choice_courses(
            ["00940412", "00940423"],
            ratings={
                "00940412": {"meanGeneralRank": "excellent"},
                "00940423": {"meanGeneralRank": 3.0},
            },
        )

        assert ranked == ("00940423", "00940412")

    def test_course_numbers_are_normalised_before_ranking(self) -> None:
        ranked = rank_choice_courses(["940412"], ratings={"00940412": {"meanGeneralRank": 4.0}})

        assert ranked == ("00940412",)


class TestMomentum:
    def test_a_chain_the_student_has_started_leads_its_bucket(self) -> None:
        """The closest thing this data has to "because you watched that".
        One real student has taken 3 of Chain B and 0 of Chain C, and Chain C
        led purely because "C" sorts before "B" by title."""
        shelves = build_course_shelves(
            requirement_progress=[_bucket("p:elective-faculty", "Faculty electives")],
            pool_documents=[
                _pool("p:chain-a", "p:elective-faculty", "A chain", "00960111", "00960222"),
                _pool("p:chain-b", "p:elective-faculty", "B chain", "00960333", "00960444"),
            ],
            completed_course_numbers={"00960333"},
        )

        assert [shelf.title for shelf in shelves] == ["B chain", "A chain"]
        assert shelves[0].started_count == 1
        assert shelves[0].pool_size == 2

    def test_momentum_counts_the_whole_pool_not_what_is_left(self) -> None:
        """"3 of 19 taken" needs the original size; the shelf's own course list
        has already had the completed ones removed."""
        shelves = build_course_shelves(
            requirement_progress=[_bucket("p:elective-faculty", "Faculty electives")],
            pool_documents=[
                _pool("p:chain", "p:elective-faculty", "Chain", "00960111", "00960222", "00960333")
            ],
            completed_course_numbers={"00960111"},
        )

        assert (shelves[0].started_count, shelves[0].pool_size) == (1, 3)
        assert len(shelves[0].course_numbers) == 2

    def test_untouched_pools_keep_a_stable_alphabetical_order(self) -> None:
        shelves = build_course_shelves(
            requirement_progress=[_bucket("p:elective-faculty", "Faculty electives")],
            pool_documents=[
                _pool("p:z", "p:elective-faculty", "Z chain", "00960111"),
                _pool("p:a", "p:elective-faculty", "A chain", "00960222"),
            ],
        )

        assert [shelf.title for shelf in shelves] == ["A chain", "Z chain"]
