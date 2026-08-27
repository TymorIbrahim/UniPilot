import { expect } from '@playwright/test'
import { BasePage } from './BasePage'

// RisksPage.tsx has no i18n today (unlike the rest of the app) — its heading
// and "Run analysis" button text are always English, in every locale.
export class RisksPage extends BasePage {
  readonly runAnalysisButton = this.page.getByRole('button', { name: /Run analysis/i })
  readonly explainButton = this.page.getByTestId('explain-risk-button')
  readonly explainStatus = this.page.getByTestId('explain-risk-status')
  readonly explainNarrative = this.page.getByTestId('explain-risk-narrative')
  readonly explainError = this.page.getByTestId('explain-risk-error')

  async gotoRisks() {
    await this.goto('/risks')
    await expect(this.heading(/Academic risks/i)).toBeVisible()
  }

  async runAnalysis() {
    const analyzeResponse = this.page.waitForResponse(
      (response) => response.url().includes('/academic-risks/analyze') && response.status() === 201,
      { timeout: 20_000 },
    )
    await this.runAnalysisButton.click()
    await analyzeResponse
  }

  async explainAnalysis() {
    const enqueueResponse = this.page.waitForResponse(
      (response) =>
        response.url().includes('/ai-jobs') &&
        response.request().method() === 'POST' &&
        response.status() === 202,
      { timeout: 15_000 },
    )
    await this.explainButton.click()
    await enqueueResponse
    await expect(this.explainNarrative).toBeVisible({ timeout: 20_000 })
  }
}
