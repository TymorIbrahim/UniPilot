"""The demo catalog a visitor to the live gallery demo actually sees."""

from __future__ import annotations

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.config import Settings
from app.db.dds_demo_seed import (
    DEMO_SEED_COLLECTIONS,
    load_demo_catalog,
    seed_dds_demo_catalog,
)


@pytest.fixture
def payload():
    return load_demo_catalog()


@pytest.fixture
def settings():
    return Settings(environment="development", auto_seed_catalog=True)


@pytest.fixture
def database():
    return AsyncMongoMockClient()["demo_seed_test"]


def test_every_seeded_collection_has_documents(payload):
    empty = [name for name in DEMO_SEED_COLLECTIONS if not payload.get(name)]
    assert empty == []


def test_the_three_dds_tracks_are_present(payload):
    codes = {program["programCode"] for program in payload["degree_programs"]}
    assert codes == {"009216-1-000", "009009-1-000", "009118-1-000"}


def test_the_only_courses_a_rule_names_but_the_catalog_lacks_are_excluded_ones(payload):
    """A dangling reference renders a blank row, so each one must be deliberate.

    Production has exactly this shape: the promoter purges the vault-excluded
    course numbers but leaves the rules that reference them, so the demo matching
    that is correct. Anything *else* dangling is a generator bug.
    """
    from app.catalog.excluded_courses import PRODUCTION_EXCLUDED_COURSE_NUMBERS

    known = {course["courseNumber"] for course in payload["courses"]}
    referenced = {
        reference["courseNumber"]
        for group in payload["degree_requirements"] + payload["catalog_rules"]
        for reference in group.get("courseReferences") or []
        if reference.get("courseNumber")
    }
    assert referenced - known - PRODUCTION_EXCLUDED_COURSE_NUMBERS == set()


def test_no_production_excluded_course_is_seeded(payload):
    """Seeding one would show the `ai` service a course no visitor can see."""
    from app.catalog.excluded_courses import PRODUCTION_EXCLUDED_COURSE_NUMBERS

    seeded = {course["courseNumber"] for course in payload["courses"]}
    assert seeded & PRODUCTION_EXCLUDED_COURSE_NUMBERS == set()


def test_credit_buckets_are_enforceable_and_rules_are_not(payload):
    """The progress calculator must never enforce advisory guidance."""
    for requirement in payload["degree_requirements"]:
        assert requirement["ruleExpression"]["type"] == "credit_bucket"
        assert requirement["advisoryOnly"] is False
        assert requirement["minCredits"] is not None

    for rule in payload["catalog_rules"]:
        assert rule["ruleExpression"]["type"] != "credit_bucket"
        assert rule["advisoryOnly"] is True
        assert rule["enforceInGraduationProgress"] is False


def test_a_pool_that_claims_a_credit_bucket_points_at_a_real_one(payload):
    bucket_ids = {
        requirement["requirementGroupId"] for requirement in payload["degree_requirements"]
    }
    linked = [
        rule["linkedCreditBucketId"]
        for rule in payload["catalog_rules"]
        if rule.get("linkedCreditBucketId")
    ]
    assert linked, "expected at least one pool to fill a credit bucket"
    assert set(linked) - bucket_ids == set()


def test_each_track_path_option_links_to_a_seeded_program(payload):
    codes = {program["programCode"] for program in payload["degree_programs"]}
    linked = {
        option["linkedProgramCode"]
        for option in payload["catalog_path_options"]
        if option.get("linkedProgramCode")
    }
    assert linked == codes


def test_every_document_is_published_with_a_production_key(payload):
    for name in DEMO_SEED_COLLECTIONS:
        for document in payload[name]:
            assert document["status"] == "published", name
            assert document["productionKey"], name


def test_every_offering_belongs_to_a_seeded_course(payload):
    known = {course["courseNumber"] for course in payload["courses"]}
    orphans = {
        offering["courseNumber"]
        for offering in payload["course_offerings"]
        if offering["courseNumber"] not in known
    }
    assert orphans == set()


async def test_seeding_writes_every_collection(database, settings):
    counts = await seed_dds_demo_catalog(database, settings)

    assert counts["degree_programs"] == 3
    for name, expected in counts.items():
        collection = getattr(settings, f"{name}_collection")
        assert await database[collection].count_documents({}) == expected


async def test_seeding_is_not_repeated_into_a_populated_database(database, settings):
    await seed_dds_demo_catalog(database, settings)
    first = await database[settings.courses_collection].count_documents({})

    await seed_dds_demo_catalog(database, settings)

    assert await database[settings.courses_collection].count_documents({}) == first


async def test_the_demo_flag_seeds_dds_instead_of_the_ci_fixture(database):
    """CI and E2E assert against `catalog_bootstrap`'s fixture course numbers."""
    from app.db.catalog_bootstrap import ensure_development_catalog

    demo = Settings(environment="development", auto_seed_catalog=True, seed_demo_catalog=True)
    assert await ensure_development_catalog(database, demo) is True

    programs = await database[demo.degree_programs_collection].distinct("programCode")
    assert set(programs) == {"009216-1-000", "009009-1-000", "009118-1-000"}
    # The CI fixture seeds a CS program; the demo deliberately does not.
    assert "023023-1-000" not in programs
    assert await database[demo.courses_collection].count_documents({}) > 200


async def test_without_the_flag_the_ci_fixture_is_still_what_is_seeded(database):
    from app.db.catalog_bootstrap import CS_PROGRAM_CODE, ensure_development_catalog

    ci = Settings(environment="development", auto_seed_catalog=True)
    assert await ensure_development_catalog(database, ci) is True

    programs = await database[ci.degree_programs_collection].distinct("programCode")
    assert CS_PROGRAM_CODE in programs
    assert await database[ci.courses_collection].count_documents({}) < 50
