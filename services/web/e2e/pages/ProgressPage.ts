import { expect } from '@playwright/test'
import { BasePage } from './BasePage'

export class ProgressPage extends BasePage {
  readonly summaryCard = this.page.getByTestId('progress-summary-card')
  readonly poolsPanel = this.page.getByTestId('elective-pools-panel')
  readonly recommendCoursesButton = this.page.getByTestId('recommend-courses-button')
  readonly recommendCoursesStatus = this.page.getByTestId('recommend-courses-status')
  readonly recommendCoursesNarrative = this.page.getByTestId('recommend-courses-narrative')
  readonly attentionPanel = this.page.getByTestId('progress-attention-panel')
  readonly attentionLink = this.page.getByTestId('progress-summary-attention-link')

  async gotoProgress() {
    await this.goto('/progress')
    await expect(this.summaryCard).toBeVisible({ timeout: 20_000 })
  }

  async gotoProgressWithPool(poolId: string) {
    await this.goto(`/progress?pool=${encodeURIComponent(poolId)}`)
    await expect(this.summaryCard).toBeVisible({ timeout: 20_000 })
  }

  async expectCoreSections() {
    await expect(this.heading(/התקדמות לתואר|Graduation progress/i)).toBeVisible()
    await expect(this.page.getByTestId('curriculum-graph-section')).toBeVisible({ timeout: 15_000 })
    await expect(this.poolsPanel).toBeVisible({ timeout: 15_000 })
  }

  async recommendCourses() {
    await expect(this.recommendCoursesButton).toBeVisible({ timeout: 15_000 })
    const enqueueResponse = this.page.waitForResponse(
      (response) =>
        response.url().includes('/ai-jobs') &&
        response.request().method() === 'POST' &&
        response.status() === 202,
      { timeout: 15_000 },
    )
    await this.recommendCoursesButton.click()
    await enqueueResponse
    await expect(this.recommendCoursesNarrative).toBeVisible({ timeout: 20_000 })
  }
}
