import { expect, test } from './fixtures/test'
import { E2E_PLANNER_SEMESTER } from './helpers/planner'

/**
 * Academic risk analysis + "Explain in plain language" async AI job pipeline.
 * Requires a saved semester plan before "Run analysis" is enabled.
 */
test.describe('Academic risks — explain in plain language', () => {
  test.beforeEach(async ({ plannerPage }) => {
    await plannerPage.openSavedPlanForEdit(E2E_PLANNER_SEMESTER)
  })

  test('runs analysis, enqueues an AI job, and renders the narrative', async ({ risksPage }) => {
    await risksPage.gotoRisks()
    await risksPage.runAnalysis()

    await expect(risksPage.explainButton).toBeVisible()
    await risksPage.explainAnalysis()

    await expect(risksPage.explainNarrative).not.toBeEmpty()
    await expect(risksPage.explainStatus).not.toBeVisible()
    await expect(risksPage.explainError).not.toBeVisible()
  })
})
