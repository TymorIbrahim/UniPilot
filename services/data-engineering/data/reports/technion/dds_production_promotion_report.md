# DDS Production Promotion Report (Phase 12)

Promotion run: `dds-promotion-51279ef0711d`
Started: 2026-08-29T20:21:46+00:00
Finished: 2026-08-29T20:21:48+00:00
Status: **completed**
Gate status: **pass-with-warnings**
Dry run: **False**
Confirmation flag: **True**
Production writes performed: **True**

## Policies applied
- nonExecutableRulesPolicy: `advisory-only`
- enforceNonExecutableRulesInProduction: `False`
- productionExcludedCoursePolicy: `omit-from-production-do-not-ingest`
- productionExcludedCourseNumbers: 34

## Counts planned
- degreePrograms: 3
- catalogPathOptions: 31
- catalogFaculties: 1
- hardDegreeRequirements: 16
- advisoryCatalogRules: 56
- courses: 2628
- courseOfferings: 6638
- skippedItems: 90
- skippedExcludedCourses: 34

## Counts written
- degree_programs: 3
- degree_requirements: 16
- catalog_rules: 59
- courses: 2628
- course_offerings: 6638

## Production collection counts
### Before
- catalog_faculties: 17
- catalog_path_options: 273
- catalog_rules: 1018
- course_offerings: 6564
- courses: 2610
- degree_programs: 61
- degree_requirements: 321
- promotion_runs: 18
### After
- catalog_faculties: 17
- catalog_path_options: 273
- catalog_rules: 1027
- course_offerings: 6638
- courses: 2628
- degree_programs: 61
- degree_requirements: 321
- promotion_runs: 19

## Skipped excluded courses
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

## Advisory rule handling
- Non-executable groups promoted to `catalog_rules` with `enforceInGraduationProgress: false`.

## Rollback notes
- Delete production docs with promotionRunId=dds-promotion-51279ef0711d to roll back this run.
- Do not delete staging data.
- Advisory catalog rules remain non-enforced in graduation progress.

## Safety
- Staging collections were not modified.
- Production promotion used stable `productionKey` upserts.
- Roll back with `rollback-dds-production-promotion --promotion-run-id <id> --i-confirm-dangerous-production-write` (deletes only matching promotionRunId).
