import { expect } from '@playwright/test'
import { BasePage } from './BasePage'

// RisksPage.tsx has no i18n today (unlike the rest of the app) — its heading
// and "Run analysis" button text are always English, in every locale.
export class RisksPage extends BasePage {
  readonly runAnalysisButton = this.page.getByRole('button', { name: /Run analysis/i })

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

}
