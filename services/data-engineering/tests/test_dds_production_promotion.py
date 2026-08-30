"""Tests for Phase 12 guarded DDS production promotion."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import get_settings
from app.curation.catalog_policies import PRODUCTION_EXCLUDED_COURSE_NUMBERS
from app.importers.dds_catalog_staging_importer import PROMOTION_WRITE_COLLECTIONS
from app.main import run_promote_dds_to_production, run_rollback_dds_production_promotion
from app.promotion.dds_production_promoter import (
    ProductionPromotionError,
    _build_core_mandatory_pool_documents,
    _retire_superseded_catalog_rules,
    run_dds_production_promotion,
    run_dds_production_rollback,
    validate_production_collections_for_promotion,
    _validate_document_safety,
)
from tests.test_dds_promotion_gate import (
    EXPECTED_PROGRAMS,
    HARD_GROUP_IDS,
    SEED_ADVISORY_GROUP_IDS,
    _seed_signed_off_promotion_staging,
)


def test_promote_refuses_without_dangerous_flag(mongo_database, monkeypatch) -> None:
    _seed_signed_off_promotion_staging(mongo_database)
    monkeypatch.setattr("app.main.check_mongo_connectivity", lambda: "connected")
    before = sum(mongo_database[name].count_documents({}) for name in PROMOTION_WRITE_COLLECTIONS)
    exit_code = run_promote_dds_to_production(False, False, True, None, None)
    after = sum(mongo_database[name].count_documents({}) for name in PROMOTION_WRITE_COLLECTIONS)
    assert exit_code == 2
    assert before == after == 0


def test_dry_run_writes_no_production_documents(mongo_database, tmp_path: Path) -> None:
    _seed_signed_off_promotion_staging(mongo_database)
    result = run_dds_production_promotion(
        mongo_database,
        dry_run=True,
        allow_warnings=True,
        json_path=tmp_path / "report.json",
        md_path=tmp_path / "report.md",
    )
    assert result.productionWritesPerformed is False
    assert result.promotionRun.status == "completed"
    assert sum(mongo_database[name].count_documents({}) for name in PROMOTION_WRITE_COLLECTIONS) == 0


def test_gate_is_rerun_before_promotion(mongo_database) -> None:
    _seed_signed_off_promotion_staging(mongo_database)
    result = run_dds_production_promotion(
        mongo_database,
        confirm_dangerous=True,
        dry_run=True,
        allow_warnings=True,
    )
    assert result.gate.checks
    assert result.gate.gateStatus in {"pass", "pass-with-warnings"}


def test_promotion_writes_expected_collections(mongo_database) -> None:
    _seed_signed_off_promotion_staging(mongo_database)
    settings = get_settings()
    result = run_dds_production_promotion(
        mongo_database,
        confirm_dangerous=True,
        allow_warnings=True,
    )
    assert result.productionWritesPerformed is True
    assert result.promotionRun.status == "completed"
    assert mongo_database[settings.production_degree_programs_collection].count_documents({}) == 3
    assert (
        mongo_database[settings.production_degree_requirements_collection].count_documents({})
        == len(HARD_GROUP_IDS)
    )
    assert mongo_database[settings.production_catalog_rules_collection].count_documents({}) > 0
    unique_groups = len(
        mongo_database[settings.production_catalog_rules_collection].distinct("requirementGroupId")
    )
    assert unique_groups == mongo_database[settings.production_catalog_rules_collection].count_documents({})
    staged_courses = mongo_database[settings.staging_courses_collection].count_documents({})
    staged_offerings = mongo_database[settings.staging_course_offerings_collection].count_documents({})
    assert mongo_database[settings.production_courses_collection].count_documents({}) == staged_courses
    assert (
        mongo_database[settings.production_course_offerings_collection].count_documents({})
        == staged_offerings
    )
    assert mongo_database[settings.production_promotion_runs_collection].count_documents({}) == 1


def test_promotion_writes_advisory_requirement_group_record_type(mongo_database) -> None:
    _seed_signed_off_promotion_staging(mongo_database)
    settings = get_settings()
    run_dds_production_promotion(mongo_database, confirm_dangerous=True, allow_warnings=True)
    record_types = mongo_database[settings.production_catalog_rules_collection].distinct("recordType")
    assert record_types == ["advisory_requirement_group"]


def test_idempotent_rerun_does_not_duplicate(mongo_database) -> None:
    _seed_signed_off_promotion_staging(mongo_database)
    settings = get_settings()
    first = run_dds_production_promotion(mongo_database, confirm_dangerous=True, allow_warnings=True)
    counts_after_first = {
        name: mongo_database[name].count_documents({}) for name in PROMOTION_WRITE_COLLECTIONS
    }
    second = run_dds_production_promotion(mongo_database, confirm_dangerous=True, allow_warnings=True)
    counts_after_second = {
        name: mongo_database[name].count_documents({}) for name in PROMOTION_WRITE_COLLECTIONS
    }
    assert first.productionWritesPerformed is True
    assert second.productionWritesPerformed is True
    assert counts_after_first == counts_after_second


def test_excluded_courses_are_skipped(mongo_database) -> None:
    _seed_signed_off_promotion_staging(mongo_database)
    settings = get_settings()
    run_dds_production_promotion(mongo_database, confirm_dangerous=True, allow_warnings=True)
    for number in PRODUCTION_EXCLUDED_COURSE_NUMBERS[:2]:
        assert (
            mongo_database[settings.production_courses_collection].count_documents(
                {"courseNumber": number}
            )
            == 0
        )


def test_purge_production_excluded_courses_removes_leaked_rows(mongo_database) -> None:
    from app.promotion.dds_production_promoter import purge_production_excluded_courses

    settings = get_settings()
    leaked = PRODUCTION_EXCLUDED_COURSE_NUMBERS[0]
    mongo_database[settings.production_courses_collection].insert_one(
        {"courseNumber": leaked, "productionKey": f"technion:course:{leaked}", "status": "published"}
    )
    mongo_database[settings.production_course_offerings_collection].insert_one(
        {
            "courseNumber": leaked,
            "productionKey": f"technion:course-offering:{leaked}:2025:201",
            "status": "published",
        }
    )

    deleted = purge_production_excluded_courses(mongo_database, settings=settings)
    assert deleted["courses"] >= 1
    assert deleted["course_offerings"] >= 1
    assert (
        mongo_database[settings.production_courses_collection].count_documents(
            {"courseNumber": leaked}
        )
        == 0
    )


def test_purge_production_excluded_courses_noop_for_empty_set(mongo_database) -> None:
    from app.promotion.dds_production_promoter import purge_production_excluded_courses

    settings = get_settings()
    assert purge_production_excluded_courses(
        mongo_database,
        settings=settings,
        excluded_course_numbers=set(),
    ) == {"courses": 0, "course_offerings": 0}


def test_offerings_for_excluded_courses_are_skipped(mongo_database) -> None:
    _seed_signed_off_promotion_staging(mongo_database)
    settings = get_settings()
    excluded = PRODUCTION_EXCLUDED_COURSE_NUMBERS[0]
    mongo_database[settings.staging_course_offerings_collection].insert_one(
        {
            "stagingKey": f"technion:course-offering:{excluded}:2025:201",
            "courseNumber": excluded,
            "academicYear": 2025,
            "semesterCode": 201,
            "semesterName": "spring",
            "isStaging": True,
            "productionEligible": False,
        }
    )
    run_dds_production_promotion(mongo_database, confirm_dangerous=True, allow_warnings=True)
    assert (
        mongo_database[settings.production_course_offerings_collection].count_documents(
            {"courseNumber": excluded}
        )
        == 0
    )


def test_advisory_rules_are_non_enforced(mongo_database) -> None:
    _seed_signed_off_promotion_staging(mongo_database)
    settings = get_settings()
    run_dds_production_promotion(mongo_database, confirm_dangerous=True, allow_warnings=True)
    enforced = mongo_database[settings.production_catalog_rules_collection].count_documents(
        {"enforceInGraduationProgress": True}
    )
    assert enforced == 0
    advisory = mongo_database[settings.production_catalog_rules_collection].count_documents(
        {"advisoryOnly": True}
    )
    assert advisory >= len(SEED_ADVISORY_GROUP_IDS)


def test_graduation_linked_pools_promoted_with_explicit_bucket_ids(mongo_database) -> None:
    _seed_signed_off_promotion_staging(mongo_database)
    settings = get_settings()
    run_dds_production_promotion(mongo_database, confirm_dangerous=True, allow_warnings=True)
    ds_pool = mongo_database[settings.production_catalog_rules_collection].find_one(
        {"requirementGroupId": "009216-1-000:elective-ds-pool"}
    )
    faculty_pool = mongo_database[settings.production_catalog_rules_collection].find_one(
        {"requirementGroupId": "009216-1-000:elective-faculty-pool"}
    )
    assert ds_pool is not None
    ds_linked = ds_pool.get("linkedCreditBucketId") or ds_pool.get("sourceMetadata", {}).get(
        "linkedCreditBucketId"
    )
    assert ds_linked == "009216-1-000:elective-ds"
    assert faculty_pool is not None
    faculty_linked = faculty_pool.get("linkedCreditBucketId") or faculty_pool.get(
        "sourceMetadata", {}
    ).get("linkedCreditBucketId")
    assert faculty_linked == "009216-1-000:elective-faculty"


def test_hard_requirements_are_executable_only(mongo_database) -> None:
    _seed_signed_off_promotion_staging(mongo_database)
    settings = get_settings()
    run_dds_production_promotion(mongo_database, confirm_dangerous=True, allow_warnings=True)
    for group_id in SEED_ADVISORY_GROUP_IDS:
        assert (
            mongo_database[settings.production_degree_requirements_collection].count_documents(
                {"requirementGroupId": group_id}
            )
            == 0
        )
    hard = mongo_database[settings.production_degree_requirements_collection].count_documents(
        {"ruleIsExecutable": True}
    )
    assert hard == len(HARD_GROUP_IDS)


def test_production_docs_exclude_staging_flags(mongo_database) -> None:
    _seed_signed_off_promotion_staging(mongo_database)
    settings = get_settings()
    run_dds_production_promotion(mongo_database, confirm_dangerous=True, allow_warnings=True)
    sample = mongo_database[settings.production_courses_collection].find_one({})
    assert sample is not None
    assert "isStaging" not in sample
    assert "productionEligible" not in sample
    assert sample.get("promotionRunId")
    assert sample.get("promotedAt")


def test_no_degree_requirements_inferred_from_course_json() -> None:
    with pytest.raises(ProductionPromotionError):
        _validate_document_safety(
            {"metadata": {"degreeRequirementsInferred": True}},
            context="course",
        )


def test_production_promotion_records_failure_on_write_error(mongo_database, monkeypatch) -> None:
    _seed_signed_off_promotion_staging(mongo_database)

    def boom(*args, **kwargs):
        raise RuntimeError("write failed")

    monkeypatch.setattr(
        "app.promotion.dds_production_promoter._upsert_production_documents",
        boom,
    )
    result = run_dds_production_promotion(
        mongo_database,
        confirm_dangerous=True,
        allow_warnings=True,
    )
    assert result.promotionRun.status == "failed"
    assert "write failed" in result.promotionRun.errors[0]
    # Once the write has been entered, the run cannot claim it wrote nothing.
    # `bulk_write(ordered=False)` keeps going past a rejected document, so a
    # raising upsert may still have landed some of them. This assertion used to
    # read `is False`, and that is exactly what hid six emptied computer-science
    # programs behind a report saying no production write had occurred.
    assert result.productionWritesPerformed is True
    assert any("partially promoted" in error for error in result.promotionRun.errors)


def test_a_failure_before_any_write_still_reports_no_production_change(
    mongo_database, monkeypatch
) -> None:
    """The honest flag must distinguish the two cases, not just always say True."""

    def boom(*args, **kwargs):
        raise RuntimeError("planning failed")

    monkeypatch.setattr(
        "app.promotion.dds_production_promoter.build_production_documents",
        boom,
    )
    _seed_signed_off_promotion_staging(mongo_database)
    result = run_dds_production_promotion(
        mongo_database,
        confirm_dangerous=True,
        allow_warnings=True,
    )

    assert result.promotionRun.status == "failed"
    assert result.productionWritesPerformed is False
    assert not any("partially promoted" in error for error in result.promotionRun.errors)


def test_a_failing_promotion_leaves_the_existing_requirements_alone(
    mongo_database, monkeypatch
) -> None:
    """The regression this ordering exists to prevent: computer-science failed on
    a duplicate _id and its six programs were left with no requirement groups,
    because the retires had already run before the upsert was attempted."""
    _seed_signed_off_promotion_staging(mongo_database)
    settings = get_settings()
    requirements = mongo_database[settings.production_degree_requirements_collection]
    requirements.insert_one(
        {
            "productionKey": "incumbent-requirement",
            "programCode": "023044-1-000",
            "requirementGroupId": "023044-1-000:required",
            "minCredits": 84.0,
            "sourceName": "technion-dds-catalog",
            "catalogVersion": "2025-2026",
        }
    )

    monkeypatch.setattr(
        "app.promotion.dds_production_promoter._upsert_production_documents",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("duplicate key")),
    )
    result = run_dds_production_promotion(
        mongo_database,
        confirm_dangerous=True,
        allow_warnings=True,
    )

    assert result.promotionRun.status == "failed"
    assert requirements.count_documents({"productionKey": "incumbent-requirement"}) == 1


def test_conflicting_production_data_is_retired_on_repromotion(mongo_database) -> None:
    _seed_signed_off_promotion_staging(mongo_database)
    settings = get_settings()
    mongo_database[settings.production_degree_programs_collection].insert_one(
        {
            "productionKey": "legacy-program",
            "programCode": "legacy",
            "catalogVersion": "2099-2099",
            "sourceName": "technion-dds-catalog",
        }
    )
    result = run_dds_production_promotion(
        mongo_database,
        confirm_dangerous=True,
        allow_warnings=True,
    )
    assert result.productionWritesPerformed is True
    assert result.promotionRun.status == "completed"
    assert (
        mongo_database[settings.production_degree_programs_collection].count_documents(
            {"productionKey": "legacy-program"}
        )
        == 0
    )


def test_conflicting_catalog_version_fails(mongo_database) -> None:
    _seed_signed_off_promotion_staging(mongo_database)
    settings = get_settings()
    from app.catalog.faculty_catalog_context import production_program_key

    conflicting_key = production_program_key("dds", "009216-1-000", "2025-2026")
    mongo_database[settings.production_degree_programs_collection].insert_one(
        {
            "productionKey": conflicting_key,
            "programCode": "009216-1-000",
            "catalogVersion": "2099-2099",
            "sourceName": "technion-dds-catalog",
        }
    )
    result = run_dds_production_promotion(
        mongo_database,
        confirm_dangerous=True,
        allow_warnings=True,
    )
    assert result.productionWritesPerformed is True
    assert result.promotionRun.status == "completed"
    promoted = mongo_database[settings.production_degree_programs_collection].find_one(
        {"productionKey": conflicting_key}
    )
    assert promoted is not None
    assert promoted["catalogVersion"] == "2025-2026"


def test_rollback_requires_dangerous_flag(mongo_database) -> None:
    summary = run_dds_production_rollback(
        mongo_database,
        promotion_run_id="missing",
        confirm_dangerous=False,
    )
    assert "error" in summary


def test_rollback_deletes_only_matching_promotion_run_id(mongo_database) -> None:
    _seed_signed_off_promotion_staging(mongo_database)
    settings = get_settings()
    result = run_dds_production_promotion(mongo_database, confirm_dangerous=True, allow_warnings=True)
    run_id = result.promotionRun.promotionRunId
    mongo_database[settings.production_degree_programs_collection].insert_one(
        {
            "productionKey": "foreign",
            "promotionRunId": "other-run",
            "programCode": "foreign",
        }
    )
    summary = run_dds_production_rollback(
        mongo_database,
        promotion_run_id=run_id,
        confirm_dangerous=True,
    )
    assert summary["status"] == "rolled_back"
    assert mongo_database[settings.production_degree_programs_collection].count_documents({}) == 1
    assert (
        mongo_database[settings.production_degree_programs_collection].find_one({})["promotionRunId"]
        == "other-run"
    )


def test_validate_production_collections_rejects_foreign_docs(mongo_database) -> None:
    settings = get_settings()
    mongo_database[settings.production_degree_programs_collection].insert_one(
        {
            "productionKey": "technion-dds:program:legacy:2025-2026",
            "sourceName": "technion-dds-catalog",
            "legacy": True,
        }
    )
    with pytest.raises(ProductionPromotionError):
        validate_production_collections_for_promotion(
            mongo_database,
            settings=settings,
            planned_keys_by_collection={
                settings.production_degree_programs_collection: {
                    "technion-dds:program:009216-1-000:2025-2026"
                }
            },
            catalog_version="2025-2026",
            source_name="technion-dds-catalog",
        )


def test_retire_superseded_catalog_rules_is_faculty_scoped(mongo_database) -> None:
    settings = get_settings()
    collection = settings.production_catalog_rules_collection
    mongo_database[collection].insert_many(
        [
            {
                "productionKey": "technion-dds:advisory-rule:req:009216-1-000:semester-1-matrix:2025-2026",
                "sourceName": "technion-dds-catalog",
                "catalogVersion": "2025-2026",
            },
            {
                "productionKey": "technion-computer-science:advisory-rule:req:023023-1-000:semester-1-matrix:2025-2026",
                "sourceName": "technion-computer-science-catalog",
                "catalogVersion": "2025-2026",
            },
        ]
    )

    removed = _retire_superseded_catalog_rules(
        mongo_database,
        settings=settings,
        planned_production_keys={
            "technion-computer-science:advisory-rule:req:023023-1-000:cs-spec-group-01:2025-2026"
        },
        catalog_version="2025-2026",
        catalog_source_name="technion-computer-science-catalog",
    )
    assert removed == 1
    assert (
        mongo_database[collection].count_documents({"sourceName": "technion-dds-catalog"})
        == 1
    )
    assert (
        mongo_database[collection].count_documents(
            {"sourceName": "technion-computer-science-catalog"}
        )
        == 0
    )


def test_retire_superseded_catalog_rules_retires_legacy_rows_missing_source_name(
    mongo_database,
) -> None:
    """A pre-`sourceName` legacy row for a group we're about to re-promote must not
    survive as an orphaned duplicate just because it fails the sourceName filter."""
    settings = get_settings()
    collection = settings.production_catalog_rules_collection
    mongo_database[collection].insert_one(
        {
            "productionKey": "technion-dds:advisory:009216-1-000:semester-1-matrix:2025-2026",
            "requirementGroupId": "009216-1-000:semester-1-matrix",
            "catalogVersion": "2025-2026",
            "courseReferences": [],
        }
    )

    removed = _retire_superseded_catalog_rules(
        mongo_database,
        settings=settings,
        planned_production_keys={
            "technion-dds:advisory-rule:req:009216-1-000:semester-1-matrix:2025-2026"
        },
        catalog_version="2025-2026",
        catalog_source_name="technion-dds-catalog",
        planned_group_ids={"009216-1-000:semester-1-matrix"},
    )
    assert removed == 1
    assert (
        mongo_database[collection].count_documents(
            {"productionKey": "technion-dds:advisory:009216-1-000:semester-1-matrix:2025-2026"}
        )
        == 0
    )


def test_retire_superseded_catalog_rules_keeps_legacy_rows_for_other_groups(
    mongo_database,
) -> None:
    """A legacy row missing sourceName must only be retired when it belongs to a
    group this run is actually re-promoting -- not any missing-sourceName row."""
    settings = get_settings()
    collection = settings.production_catalog_rules_collection
    mongo_database[collection].insert_one(
        {
            "productionKey": "technion-dds:advisory:009216-1-000:unrelated-group:2025-2026",
            "requirementGroupId": "009216-1-000:unrelated-group",
            "catalogVersion": "2025-2026",
            "courseReferences": [],
        }
    )

    removed = _retire_superseded_catalog_rules(
        mongo_database,
        settings=settings,
        planned_production_keys={
            "technion-dds:advisory-rule:req:009216-1-000:semester-1-matrix:2025-2026"
        },
        catalog_version="2025-2026",
        catalog_source_name="technion-dds-catalog",
        planned_group_ids={"009216-1-000:semester-1-matrix"},
    )
    assert removed == 0
    assert (
        mongo_database[collection].count_documents(
            {"productionKey": "technion-dds:advisory:009216-1-000:unrelated-group:2025-2026"}
        )
        == 1
    )


def test_repromotion_preserves_degree_program_id_across_key_format_change(
    mongo_database,
) -> None:
    """External references (e.g. student_profiles.degreeId) must survive a
    productionKey format change: re-promoting an existing program should update
    it in place, not silently delete-and-reinsert under a new _id."""
    _seed_signed_off_promotion_staging(mongo_database)
    settings = get_settings()
    from bson import ObjectId

    legacy_id = ObjectId()
    mongo_database[settings.production_degree_programs_collection].insert_one(
        {
            "_id": legacy_id,
            "productionKey": "technion-dds:program:legacy-key-format:009216-1-000:2025-2026",
            "institutionId": "technion",
            "programCode": "009216-1-000",
            "catalogVersion": "2025-2026",
            "sourceName": "technion-dds-catalog",
        }
    )

    result = run_dds_production_promotion(
        mongo_database,
        confirm_dangerous=True,
        allow_warnings=True,
    )
    assert result.productionWritesPerformed is True

    docs = list(
        mongo_database[settings.production_degree_programs_collection].find(
            {"programCode": "009216-1-000"}
        )
    )
    assert len(docs) == 1
    assert docs[0]["_id"] == legacy_id


def test_a_joint_programs_other_owner_does_not_have_its_id_taken(mongo_database) -> None:
    """`023323-1-000` (CS + Mathematics) is exported by BOTH faculties, and
    production holds it under whichever promoted first. Matching the identity
    lookup on programCode alone made the second faculty adopt the first's `_id`
    while writing under its own productionKey, so the upsert tried to insert a
    document whose `_id` was already taken. That E11000 is what emptied all six
    computer-science programs."""
    _seed_signed_off_promotion_staging(mongo_database)
    settings = get_settings()
    from bson import ObjectId

    other_owner_id = ObjectId()
    mongo_database[settings.production_degree_programs_collection].insert_one(
        {
            "_id": other_owner_id,
            "productionKey": "technion-mathematics:program:009216-1-000:2025-2026",
            "institutionId": "technion",
            "programCode": "009216-1-000",
            "catalogVersion": "2025-2026",
            "sourceName": "technion-mathematics-catalog",
        }
    )

    result = run_dds_production_promotion(
        mongo_database,
        confirm_dangerous=True,
        allow_warnings=True,
    )

    assert result.promotionRun.status == "completed"
    docs = list(
        mongo_database[settings.production_degree_programs_collection].find(
            {"programCode": "009216-1-000"}
        )
    )
    promoted = [d for d in docs if d.get("sourceName") == "technion-dds-catalog"]
    assert len(promoted) == 1
    assert promoted[0]["_id"] != other_owner_id
    # The other faculty's document is not this promotion's to touch.
    assert (
        mongo_database[settings.production_degree_programs_collection].count_documents(
            {"_id": other_owner_id}
        )
        == 1
    )


def test_a_faculty_may_own_its_own_catalog_rows(mongo_database) -> None:
    """The expected sourceName for catalog collections is the promoting faculty's
    own, not a hardcoded `technion-dds-catalog`. Every faculty writes its own, and
    the DDS-shaped expectation only ever passed because this validation ran before
    the write that contradicted it."""
    from app.promotion.dds_production_promoter import (
        PROMOTION_COLLECTION_SOURCE_NAMES,
        validate_production_collections_for_promotion,
    )

    settings = get_settings()
    assert "catalog_faculties" not in PROMOTION_COLLECTION_SOURCE_NAMES
    assert "degree_programs" not in PROMOTION_COLLECTION_SOURCE_NAMES

    key = "technion:faculty:faculty-computer-science:2025-2026"
    mongo_database[settings.production_catalog_faculties_collection].insert_one(
        {
            "productionKey": key,
            "catalogVersion": "2025-2026",
            "sourceName": "technion-computer-science-catalog",
        }
    )

    # Must not raise: the row belongs to the faculty doing the promoting.
    validate_production_collections_for_promotion(
        mongo_database,
        settings=settings,
        planned_keys_by_collection={settings.production_catalog_faculties_collection: {key}},
        catalog_version="2025-2026",
        source_name="technion-computer-science-catalog",
    )


def test_build_core_mandatory_pool_unions_semester_matrix_course_numbers() -> None:
    program_a_semester_1 = {
        "productionKey": "technion-dds:advisory-rule:req:009216-1-000:semester-1-matrix:2025-2026",
        "institutionId": "technion",
        "programCode": "009216-1-000",
        "requirementGroupId": "009216-1-000:semester-1-matrix",
        "ruleExpression": {"type": "semester_matrix", "operator": "all_of", "semester": 1},
        "courseReferences": [{"courseNumber": "00940345"}, {"courseNumber": "01040031"}],
        "catalogYear": 2025,
        "sourceName": "technion-dds-catalog",
        "sourceType": "dds_catalog_curated_reviewed",
    }
    program_a_semester_2 = {
        "productionKey": "technion-dds:advisory-rule:req:009216-1-000:semester-2-matrix:2025-2026",
        "institutionId": "technion",
        "programCode": "009216-1-000",
        "requirementGroupId": "009216-1-000:semester-2-matrix",
        "ruleExpression": {"type": "semester_matrix", "operator": "all_of", "semester": 2},
        # duplicate course number across semesters must be deduped
        "courseReferences": [{"courseNumber": "01040031"}, {"courseNumber": "00940219"}],
        "catalogYear": 2025,
        "sourceName": "technion-dds-catalog",
        "sourceType": "dds_catalog_curated_reviewed",
    }
    unrelated_advisory_doc = {
        "productionKey": "technion-dds:advisory-rule:req:009216-1-000:elective-ds-pool:2025-2026",
        "programCode": "009216-1-000",
        "ruleExpression": {"type": "course_pool", "operator": "choose_credits"},
        "courseReferences": [{"courseNumber": "00940411"}],
    }

    pools = _build_core_mandatory_pool_documents(
        [program_a_semester_1, program_a_semester_2, unrelated_advisory_doc],
        promotion_run_id="run-1",
        promoted_at="2026-01-01T00:00:00Z",
        catalog_version="2025-2026",
    )

    assert len(pools) == 1
    pool = pools[0]
    assert pool["requirementGroupId"] == "009216-1-000:core-mandatory-pool"
    assert pool["linkedCreditBucketId"] == "009216-1-000:core-mandatory"
    assert pool["ruleExpression"]["type"] == "course_pool"
    assert pool["enforceInGraduationProgress"] is False
    numbers = sorted(ref["courseNumber"] for ref in pool["courseReferences"])
    assert numbers == ["00940219", "00940345", "01040031"]


def test_build_core_mandatory_pool_skips_programs_with_no_matrix_data() -> None:
    assert _build_core_mandatory_pool_documents(
        [], promotion_run_id="run-1", promoted_at="2026-01-01T00:00:00Z", catalog_version="2025-2026"
    ) == []


def test_promotion_writes_no_core_mandatory_pool_when_matrix_data_is_empty(mongo_database) -> None:
    """The shared seed fixture's semester_matrix groups carry no course
    references (nothing previously consumed them) -- promotion must not
    write an empty/useless core-mandatory-pool in that case."""
    _seed_signed_off_promotion_staging(mongo_database)
    settings = get_settings()

    result = run_dds_production_promotion(
        mongo_database,
        confirm_dangerous=True,
        allow_warnings=True,
    )
    assert result.productionWritesPerformed is True

    pools = list(
        mongo_database[settings.production_catalog_rules_collection].find(
            {"requirementGroupId": {"$regex": "core-mandatory-pool$"}}
        )
    )
    assert pools == []


def test_build_core_mandatory_pool_skips_a_matrix_document_with_no_program_code() -> None:
    """A semester_matrix row that names no program cannot be attributed to one.

    Silently attributing it to whichever program came last would put another
    track's mandatory courses into this one's core pool, so it is dropped.
    """
    orphan = {
        "productionKey": "technion-dds:advisory-rule:req::semester-1-matrix:2025-2026",
        "institutionId": "technion",
        "programCode": "",
        "requirementGroupId": ":semester-1-matrix",
        "ruleExpression": {"type": "semester_matrix", "operator": "all_of", "semester": 1},
        "courseReferences": [{"courseNumber": "00940345"}],
    }

    assert (
        _build_core_mandatory_pool_documents(
            [orphan],
            promotion_run_id="run-1",
            promoted_at="2026-01-01T00:00:00Z",
            catalog_version="2025-2026",
        )
        == []
    )


def test_promotion_writes_the_core_mandatory_pool_when_matrix_data_has_courses(
    mongo_database,
) -> None:
    """The pool reaches production, which nothing checked end to end.

    `test_promotion_writes_no_core_mandatory_pool_when_matrix_data_is_empty`
    pins the empty case, and the seed fixture's matrix groups carry no course
    references -- so the branch that appends these documents never ran, and the
    100% coverage gate was failing on it. Graduation progress reads this pool:
    without it the core-mandatory bucket has no course list and credits
    whatever the student completed, up to the credit minimum.
    """
    _seed_signed_off_promotion_staging(mongo_database)
    settings = get_settings()

    # Course numbers the seed also promotes, so the pool's references resolve.
    matrix_numbers = ["00940345", "01040031"]
    mongo_database[settings.staging_degree_requirements_collection].update_one(
        {"requirementGroup.groupId": "009216-1-000:semester-1-matrix"},
        {
            "$set": {
                "requirementGroup.courseReferences": [
                    {"courseNumber": number, "titleHint": f"Matrix course {number}"}
                    for number in matrix_numbers
                ]
            }
        },
    )

    result = run_dds_production_promotion(
        mongo_database,
        confirm_dangerous=True,
        allow_warnings=True,
    )
    assert result.productionWritesPerformed is True, result.promotionRun.errors

    pools = list(
        mongo_database[settings.production_catalog_rules_collection].find(
            {"requirementGroupId": "009216-1-000:core-mandatory-pool"}
        )
    )
    assert len(pools) == 1
    pool = pools[0]
    assert pool["linkedCreditBucketId"] == "009216-1-000:core-mandatory"
    assert sorted(ref["courseNumber"] for ref in pool["courseReferences"]) == matrix_numbers
