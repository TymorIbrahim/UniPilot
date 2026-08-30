"""The catalog a visitor to the live gallery demo actually sees."""

from __future__ import annotations

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.catalog.excluded_courses import PRODUCTION_EXCLUDED_COURSE_NUMBERS
from app.config import Settings
from app.db.demo_seed import (
    DEMO_SEED_COLLECTIONS,
    load_demo_catalog,
    seed_demo_catalog,
)

# The three DDS tracks are the ones the E2E onboarding flow and the demo
# recording both walk through, so they are worth naming explicitly.
DDS_TRACKS = {"009216-1-000", "009009-1-000", "009118-1-000"}


@pytest.fixture
def payload():
    return load_demo_catalog()


@pytest.fixture
def settings():
    return Settings(environment="development", auto_seed_catalog=True, seed_demo_catalog=True)


@pytest.fixture
def database():
    return AsyncMongoMockClient()["demo_seed_test"]


def test_every_seeded_collection_has_documents(payload):
    empty = [name for name in DEMO_SEED_COLLECTIONS if not payload.get(name)]
    assert empty == []


def test_the_whole_catalog_is_seeded_not_one_faculty(payload):
    """The poster advertises the real catalog; the demo has to be it."""
    programs = payload["degree_programs"]
    faculties = {p["metadata"]["facultyId"] for p in programs}

    assert len(programs) >= 40
    assert len(faculties) >= 8, f"only {len(faculties)} faculties own a program"
    assert len(payload["courses"]) >= 2000
    assert len(payload["catalog_faculties"]) == 17


def test_the_dds_tracks_are_among_the_seeded_programs(payload):
    codes = {program["programCode"] for program in payload["degree_programs"]}
    assert DDS_TRACKS <= codes


def test_program_codes_are_unique(payload):
    """A joint program is exported by both its faculties; production holds one."""
    codes = [program["programCode"] for program in payload["degree_programs"]]
    assert len(codes) == len(set(codes))


def test_the_only_courses_a_rule_names_but_the_catalog_lacks_are_excluded_ones(payload):
    """A dangling reference renders a blank row, so each one must be deliberate.

    Production has exactly this shape: the promoter purges the vault-excluded
    course numbers but leaves the rules that reference them, so the demo matching
    that is correct. Anything *else* dangling would be a generator bug -- except
    that a track may legitimately name a course the demo year does not offer, so
    those are carried into `courses` from an earlier semester instead.
    """
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


def test_every_requirement_belongs_to_a_seeded_program(payload):
    codes = {program["programCode"] for program in payload["degree_programs"]}
    owners = {
        group["programCode"]
        for group in payload["degree_requirements"] + payload["catalog_rules"]
    }
    assert owners - codes == set()


def test_a_linked_path_option_points_at_a_seeded_program(payload):
    codes = {program["programCode"] for program in payload["degree_programs"]}
    linked = {
        option["linkedProgramCode"]
        for option in payload["catalog_path_options"]
        if option.get("linkedProgramCode")
    }
    assert linked, "expected some path options to link to a program"
    assert linked - codes == set()


def test_every_document_is_published_with_a_production_key(payload):
    for name in DEMO_SEED_COLLECTIONS:
        for document in payload[name]:
            assert document["status"] == "published", name
            assert document["productionKey"], name


def test_production_keys_are_unique_within_each_collection(payload):
    """Two documents sharing a key would collide on promotion and in the demo."""
    for name in DEMO_SEED_COLLECTIONS:
        keys = [document["productionKey"] for document in payload[name]]
        assert len(keys) == len(set(keys)), name


def test_every_offering_belongs_to_a_seeded_course(payload):
    known = {course["courseNumber"] for course in payload["courses"]}
    orphans = {
        offering["courseNumber"]
        for offering in payload["course_offerings"]
        if offering["courseNumber"] not in known
    }
    assert orphans == set()


async def test_seeding_writes_every_collection(database, settings):
    counts = await seed_demo_catalog(database, settings)

    for name, expected in counts.items():
        collection = getattr(settings, f"{name}_collection")
        assert await database[collection].count_documents({}) == expected
    assert counts["degree_programs"] >= 40
    assert counts["courses"] >= 2000


async def test_seeding_is_not_repeated_into_a_populated_database(database, settings):
    await seed_demo_catalog(database, settings)
    first = await database[settings.courses_collection].count_documents({})

    await seed_demo_catalog(database, settings)

    assert await database[settings.courses_collection].count_documents({}) == first


async def test_the_demo_flag_seeds_the_real_catalog_not_the_ci_fixture(database, settings):
    from app.db.catalog_bootstrap import SEEDED_COURSE_COUNT, ensure_development_catalog

    assert await ensure_development_catalog(database, settings) is True

    courses = await database[settings.courses_collection].count_documents({})
    programs = await database[settings.degree_programs_collection].count_documents({})
    assert courses > SEEDED_COURSE_COUNT * 100
    assert programs >= 40


async def test_without_the_flag_the_ci_fixture_is_still_what_is_seeded(database):
    """The E2E suite asserts against the fixture's specific course numbers."""
    from app.db.catalog_bootstrap import CS_PROGRAM_CODE, ensure_development_catalog

    ci = Settings(environment="development", auto_seed_catalog=True)
    assert await ensure_development_catalog(database, ci) is True

    programs = await database[ci.degree_programs_collection].distinct("programCode")
    assert CS_PROGRAM_CODE in programs
    assert await database[ci.courses_collection].count_documents({}) < 50
