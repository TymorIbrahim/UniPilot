"""Unit tests for placing a pool the promoter left unlinked.

393 of 619 course pools carry no `linkedCreditBucketId`, covering 6,549 course
references across 57 programs -- the promoter resolves the link from a
hand-maintained table of pool suffixes, and only the DDS ones were ever filled
in. Rows are grouped by that link, so all 11 Computer Science specialisation
groups and its science chains were invisible.
"""

from __future__ import annotations

import pytest

from app.planning.course_shelves import infer_bucket_for_pool


def _buckets(*suffixes, program="023023-1-000"):
    return [f"{program}:{s}" for s in suffixes]


class TestElectivePools:
    @pytest.mark.parametrize(
        "pool",
        [
            "cs-spec-group-01",
            "cs-focus-chain-ml",
            "edu-faculty-elective-list-pool",
            "biology-list-a-pool",
            "matsci-hebrew-elective-subsection-01-pool",
            "ie-additional-faculty-electives",
        ],
    )
    def test_specialisation_and_elective_pools_land_on_the_elective_bucket(self, pool) -> None:
        buckets = _buckets("required", "faculty-electives", "enrichment", "free-elective")

        assert infer_bucket_for_pool(f"023023-1-000:{pool}", buckets) == (
            "023023-1-000:faculty-electives"
        )

    def test_the_elective_bucket_is_found_whatever_the_program_calls_it(self) -> None:
        """DDS says `elective-faculty`, Computer Science says `faculty-electives`."""
        buckets = _buckets("core-mandatory", "elective-faculty", "enrichment",
                           program="009118-1-000")

        assert infer_bucket_for_pool("009118-1-000:is-focus-chain-ml", buckets) == (
            "009118-1-000:elective-faculty"
        )

    def test_a_free_elective_bucket_is_not_mistaken_for_the_faculty_one(self) -> None:
        buckets = _buckets("required", "free-elective", "enrichment")

        assert infer_bucket_for_pool("023023-1-000:cs-spec-group-01", buckets) is None


class TestRequiredPools:
    @pytest.mark.parametrize("pool", ["cs-science-chain-biology", "ece-lab-courses-pool"])
    def test_science_chains_and_labs_belong_to_the_required_bucket(self, pool) -> None:
        """The scientific-course requirement is part of the 87 required credits,
        not of the electives."""
        buckets = _buckets("required", "faculty-electives")

        assert infer_bucket_for_pool(f"023023-1-000:{pool}", buckets) == "023023-1-000:required"

    def test_the_required_bucket_is_found_whatever_it_is_called(self) -> None:
        for name in ("required-courses", "mandatory-courses", "core-mandatory", "core"):
            buckets = _buckets(name, "faculty-electives")
            assert infer_bucket_for_pool(
                "023023-1-000:cs-science-chain-biology", buckets
            ) == f"023023-1-000:{name}"


class TestNamedPools:
    @pytest.mark.parametrize(
        "pool,bucket",
        [
            ("enrichment-pool", "enrichment"),
            ("free-elective-pool", "free-elective"),
            ("physical-education-pool", "physical-education"),
        ],
    )
    def test_the_generic_pools_map_to_their_own_bucket(self, pool, bucket) -> None:
        buckets = _buckets("required", "enrichment", "free-elective", "physical-education")

        assert infer_bucket_for_pool(f"023023-1-000:{pool}", buckets) == f"023023-1-000:{bucket}"


class TestRefusals:
    def test_a_pool_it_cannot_place_is_left_alone(self) -> None:
        """Guessing would attribute courses to a requirement they do not serve."""
        buckets = _buckets("required", "faculty-electives")

        assert infer_bucket_for_pool("023023-1-000:something-unfamiliar", buckets) is None

    def test_a_pool_from_another_program_is_never_placed(self) -> None:
        buckets = _buckets("faculty-electives", program="009118-1-000")

        assert infer_bucket_for_pool("023023-1-000:cs-spec-group-01", buckets) is None

    def test_a_malformed_id_is_refused(self) -> None:
        assert infer_bucket_for_pool("no-program-code", _buckets("faculty-electives")) is None


class TestElectiveVocabulary:
    def test_a_joint_program_bucket_is_recognised(self) -> None:
        buckets = _buckets("required", "electives-both-faculties", "free-elective")

        assert infer_bucket_for_pool("023023-1-000:cs-spec-group-01", buckets) == (
            "023023-1-000:electives-both-faculties"
        )

    def test_a_recommended_elective_bucket_is_recognised(self) -> None:
        buckets = _buckets("required-courses", "recommended-electives", "enrichment")

        assert infer_bucket_for_pool("023023-1-000:cs-spec-group-01", buckets) == (
            "023023-1-000:recommended-electives"
        )

    def test_free_and_technion_wide_electives_are_never_the_faculty_one(self) -> None:
        """They accept anything; a specialisation group spends the faculty
        allowance, and misplacing it would credit a requirement it cannot."""
        buckets = _buckets("free-elective", "general-technion-electives", "enrichment")

        assert infer_bucket_for_pool("023023-1-000:cs-spec-group-01", buckets) is None

    def test_the_faculty_bucket_wins_over_a_looser_match(self) -> None:
        buckets = _buckets("recommended-electives", "faculty-electives")

        assert infer_bucket_for_pool("023023-1-000:cs-spec-group-01", buckets) == (
            "023023-1-000:faculty-electives"
        )
