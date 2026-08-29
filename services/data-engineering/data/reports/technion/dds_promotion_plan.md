# DDS Production Promotion Plan (Phase 11 — Dry Run)

Generated: 2026-08-29T20:19:00+00:00
Gate status: **pass-with-warnings**
Can promote (future Phase 12): **True**

> **No production writes were performed in this phase.**

## Summary
Gate passed with warnings. Phase 12 may implement promote-dds-to-production with explicit approval and dangerous confirmation flag.

## Policies applied
- nonExecutableRulesPolicy: `advisory-only`
- enforceNonExecutableRulesInProduction: `False`
- productionExcludedCoursePolicy: `omit-from-production-do-not-ingest`
- productionExcludedCourseNumbers: 34 courses
- signedOffBy: vault-wiki at 2026-08-29T20:18:06+00:00

## Planned production writes (counts)
- degreePrograms: 3
- catalogPathOptions: 31
- catalogFaculties: 1
- hardDegreeRequirements: 16
- advisoryCatalogRules: 56
- courses: 2628
- courseOfferings: 6638
- skippedItems: 90
- skippedExcludedCourses: 34

## Target collections
- degreePrograms → `degree_programs`
- catalogPathOptions → `catalog_path_options`
- catalogFaculties → `catalog_faculties`
- hardDegreeRequirements → `degree_requirements`
- advisoryCatalogRules → `catalog_rules`
- courses → `courses`
- courseOfferings → `course_offerings`

## Advisory rule handling
- 56 rule/group identifiers promoted as **advisory-only** (enforceInGraduationProgress=false).

## Skipped / excluded courses
- `00960226` — production-excluded-by-catalog-signoff
- `00960244` — production-excluded-by-catalog-signoff
- `00960311` — production-excluded-by-catalog-signoff
- `00960335` — production-excluded-by-catalog-signoff
- `00960351` — production-excluded-by-catalog-signoff
- `00970280` — production-excluded-by-catalog-signoff
- `00980455` — production-excluded-by-catalog-signoff
- `00400314` — production-excluded-by-catalog-signoff
- `00401222` — production-excluded-by-catalog-signoff
- `00401422` — production-excluded-by-catalog-signoff
- `00401652` — production-excluded-by-catalog-signoff
- `00402731` — production-excluded-by-catalog-signoff
- `00402851` — production-excluded-by-catalog-signoff
- `00940197` — production-excluded-by-catalog-signoff
- `00960221` — production-excluded-by-catalog-signoff
- `00960251` — production-excluded-by-catalog-signoff
- `00960293` — production-excluded-by-catalog-signoff
- `00960465` — production-excluded-by-catalog-signoff
- `00960470` — production-excluded-by-catalog-signoff
- `00960692` — production-excluded-by-catalog-signoff
- ... and 14 more

## Gate checks
- [PASS] staging.program_count: Found 3 staged dds programs (expected at least 3).
- [PASS] staging.program_codes: All expected program codes present.
- [PASS] staging.total_credits: All programs have valid totalCredits.
- [PASS] staging.requirement_groups: Found 72 staged requirement groups.
- [PASS] staging.courses: Found 2635 staged courses.
- [PASS] staging.offerings: Found 6648 staged course offerings.
- [PASS] staging.safety_flags: All staging documents have isStaging=true and productionEligible=false.
- [PASS] policy.catalog_signoff_present: vaultSignoff metadata present on staged programs.
- [PASS] policy.non_executable_advisory: nonExecutableRulesPolicy is advisory-only.
- [PASS] policy.no_mandatory_non_executable: enforceNonExecutableRulesInProduction is false.
- [PASS] policy.excluded_courses_policy: productionExcludedCoursePolicy is omit-from-production-do-not-ingest.
- [PASS] policy.excluded_courses_list: Production-excluded course list matches catalog refs absent from semester JSON staging.
- [PASS] policy.non_executable_groups_signed_off: All staged non-executable groups are covered by catalog sign-off.
- [PASS] quality.no_production_blockers: No production blockers in live quality review.
- [PASS] quality.missing_title_hints: missingTitleHints is 0.
- [PASS] quality.credit_mismatches: creditMismatches is 0.
- [PASS] quality.chain_rules_preserved: No chain/focus rule violations.
- [PASS] quality.ocr_suspects: No known OCR suspect gaps.
- [PASS] production.collections_read_only: Dry-run performed without production writes.
- [FAIL] production.existing_data: Production collections already contain data: {'catalog_rules': 1018, 'completed_courses': 123, 'course_offerings': 6564, 'courses': 2610, 'degree_programs': 61, 'degree_requirements': 321, 'promotion_runs': 18, 'semester_plans': 1}
- [PASS] plan.no_excluded_courses_in_writes: Excluded courses are not in planned course writes.
- [PASS] plan.advisory_rules_not_mandatory: All advisory catalog rules have enforceInGraduationProgress=false.

## Warnings
- Production collections already contain data: {'catalog_rules': 1018, 'completed_courses': 123, 'course_offerings': 6564, 'courses': 2610, 'degree_programs': 61, 'degree_requirements': 321, 'promotion_runs': 18, 'semester_plans': 1}

## Production safety
- **No production collection writes occurred.**
- Existing production data (review only): {'catalog_rules': 1018, 'completed_courses': 123, 'course_offerings': 6564, 'courses': 2610, 'degree_programs': 61, 'degree_requirements': 321, 'promotion_runs': 18, 'semester_plans': 1}

## Rollback notes
- Phase 11 dry-run only — no production documents were written.
- Phase 12 should support promotion run id + snapshot for rollback.
- Do not delete staging data during promotion.
- Advisory catalog rules must remain non-enforced in graduation progress.

## Phase 12 recommendation
Implement `promote-dds-to-production` only after explicit approval, with `--i-confirm-dangerous-production-write` and idempotent upsert semantics.
