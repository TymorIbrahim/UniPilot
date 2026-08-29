import type { Page } from '@playwright/test'

/** Course present in AUTO_SEED catalog and promoted vault snapshots. */
export const E2E_KNOWN_COURSE = '00940345'

/**
 * DNE data-science elective, genuinely listed in `009216-1-000:elective-ds-pool`.
 *
 * Was `00940411` (הסתברות ת'), which is NOT in that pool — it is a mandatory
 * matrix course. The transcript↔progress spec therefore hit its
 * "course is not in the pool" guard on every run and skipped itself, so the
 * one test covering the transcript-to-progress path had been passing without
 * ever executing. Verified against the live catalog: in the pool's 63 refs,
 * present in `courses`, carries credits, and not a DNE matrix course.
 */
export const E2E_DNE_ELECTIVE_COURSE = '00960200'

/** Catalog course outside DNE requirement pools — triggers ineligible credit on progress. */
export const E2E_OUT_OF_POOL_COURSE = '02340117'

/** AUTO_SEED catalog offerings use Technion spring (201) for academic year 2025. */
export const E2E_PLANNER_SEMESTER = '2025-2'

export async function selectPlannerSemester(page: Page, semesterCode = E2E_PLANNER_SEMESTER) {
  await page.locator('#planner-semester').selectOption(semesterCode)
}
