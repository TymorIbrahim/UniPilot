import { AlertTriangle, CalendarClock, Gauge } from 'lucide-react'
import type { DraftSummary } from '../../types/api'
import { useTranslation } from '../../i18n'
import { formatCredits } from '../../lib/utils'

type DraftSummaryBarProps = {
  summary: DraftSummary
}

/**
 * What the student has assembled, as a whole.
 *
 * The cards answer "should I add this". Neither difficulty nor exam crowding
 * exists on a single card — both are properties of the combination, and they
 * are the part students most often get wrong.
 */
export function DraftSummaryBar({ summary }: DraftSummaryBarProps) {
  const { t } = useTranslation()

  if (summary.plannedCourseCount === 0) return null

  const { difficulty, exams } = summary

  return (
    <aside
      className="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-muted)] px-4 py-2.5 text-xs"
      data-testid="draft-summary-bar"
    >
      <span className="font-medium text-[var(--color-text)]">
        {t('planner.shelves.draft.courses', {
          count: summary.plannedCourseCount,
          credits: formatCredits(summary.plannedCredits),
        })}
      </span>

      {difficulty ? (
        <span className="flex items-center gap-1.5 text-[var(--color-text-muted)]">
          <Gauge className="h-3.5 w-3.5 shrink-0" />
          <span className="tabular-nums">
            {t('planner.shelves.draft.difficulty', {
              mean: difficulty.plannedMean,
              max: difficulty.scaleMax,
            })}
          </span>
          {difficulty.yourCompletedMean != null ? (
            <span>
              (
              {t('planner.shelves.draft.difficultyVsYou', {
                mean: difficulty.yourCompletedMean,
              })}
              )
            </span>
          ) : null}
          {/* 31% of the catalog is rated: a mean over one of four courses is
              not a description of the semester, so the basis is stated. */}
          {difficulty.ratedCourses < difficulty.plannedCourses ? (
            <span className="text-[11px]">
              {t('planner.shelves.draft.difficultyCoverage', {
                rated: difficulty.ratedCourses,
                planned: difficulty.plannedCourses,
              })}
            </span>
          ) : null}
        </span>
      ) : null}

      {difficulty?.heavierThanUsual ? (
        <span className="flex items-center gap-1.5 text-[var(--color-warning-text)]">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
          {t('planner.shelves.draft.heavier')}
        </span>
      ) : null}

      {exams && exams.tightestGapDays != null && exams.tightestPair ? (
        <span className="flex items-center gap-1.5 text-[var(--color-warning-text)]">
          <CalendarClock className="h-3.5 w-3.5 shrink-0" />
          {t('planner.shelves.draft.examTight', {
            days: exams.tightestGapDays,
            courses: exams.tightestPair.join(', '),
          })}
        </span>
      ) : null}

      {exams && exams.withoutPublishedExam > 0 ? (
        <span className="text-[var(--color-text-muted)]">
          {t('planner.shelves.draft.examMissing', { count: exams.withoutPublishedExam })}
        </span>
      ) : null}
    </aside>
  )
}
