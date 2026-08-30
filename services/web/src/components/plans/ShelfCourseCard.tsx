import { AlertTriangle, Calendar, Info, KeyRound, Lock, Mail, Plus, Repeat } from 'lucide-react'
import type { CourseShelf, ShelfCourse } from '../../types/api'
import type { Locale } from '../../i18n/types'
import { useTranslation } from '../../i18n'
import { cn, formatCredits } from '../../lib/utils'
import { Button } from '../ui/Button'
import { semesterLabel } from '../../lib/shelves'

type ShelfCourseCardProps = {
  course: ShelfCourse
  kind: CourseShelf['kind']
  locale: Locale
  alreadyInPlan: boolean
  onAdd: (course: ShelfCourse) => void
  onInfo: (courseNumber: string) => void
}

/**
 * One course, framed by what its row is actually asking.
 *
 * A mandatory card answers "when" — the student must pass it eventually, so it
 * leads with the cost of postponing. A choice card answers "which", so it leads
 * with what previous students scored and thought. The same course can appear in
 * both roles and should not read the same way in each.
 */
export function ShelfCourseCard({
  course,
  kind,
  locale,
  alreadyInPlan,
  onAdd,
  onInfo,
}: ShelfCourseCardProps) {
  const { t } = useTranslation()
  const title = (locale === 'he' ? course.titleHebrew : course.title) || course.title || ''
  const reviews = course.signal?.reviews
  const published = course.signal?.published
  const isMandatory = kind === 'mandatory'

  return (
    <article
      className={cn(
        'flex w-64 shrink-0 flex-col gap-2 rounded-xl border border-[var(--color-border)]',
        'bg-[var(--color-surface-muted)] p-3 transition',
        'hover:border-[var(--color-primary)]/40 hover:bg-white',
        alreadyInPlan && 'opacity-60',
      )}
      data-testid={`shelf-card-${course.courseNumber}`}
    >
      <header className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-mono text-[11px] font-semibold text-[var(--color-primary)]">
            {course.courseNumber}
          </p>
          <h4 className="mt-0.5 line-clamp-2 text-sm font-medium leading-snug text-[var(--color-text)]">
            {title}
          </h4>
        </div>
        {course.credits != null ? (
          <span className="shrink-0 text-[11px] tabular-nums text-[var(--color-text-muted)]">
            {formatCredits(course.credits)}
          </span>
        ) : null}
      </header>

      {course.reasons.length > 0 ? (
        <ul className="flex flex-wrap gap-1">
          {course.reasons.map((reason) => (
            <li
              key={reason}
              className="rounded-full bg-[var(--color-primary)]/10 px-2 py-0.5 text-[10px] font-medium text-[var(--color-primary)]"
            >
              {t(`planner.shelves.reason.${reason}` as 'planner.shelves.reason.well_reviewed')}
            </li>
          ))}
        </ul>
      ) : null}

      {isMandatory && course.deferral ? (
        <dl className="space-y-1 text-[11px] text-[var(--color-text-muted)]">
          <div className="flex items-center gap-1.5">
            <Calendar className="h-3 w-3 shrink-0" />
            <dd>
              {course.deferral.nextOffering
                ? t('planner.shelves.nextRuns', {
                    term: semesterLabel(course.deferral.nextOffering, t),
                  })
                : t('planner.shelves.nextUnknown')}
            </dd>
          </div>
          {course.deferral.dependentCount > 0 ? (
            <div className="flex items-center gap-1.5">
              <Lock className="h-3 w-3 shrink-0" />
              <dd>
                {course.deferral.dependentCount === 1
                  ? t('planner.shelves.gatesOne')
                  : t('planner.shelves.gates', { count: course.deferral.dependentCount })}
              </dd>
            </div>
          ) : null}
        </dl>
      ) : (
        <dl className="space-y-1 text-[11px] text-[var(--color-text-muted)]">
          {reviews ? (
            <dd>
              {t('planner.shelves.reviewsShort', {
                score: reviews.meanGeneralRank,
                max: reviews.scaleMax,
                count: reviews.responseCount,
              })}
            </dd>
          ) : null}
          {published ? (
            <dd className="tabular-nums">
              {t('planner.shelves.passRateShort', {
                rate: Math.round(published.passRate * 100),
                average: Math.round(published.averageGrade),
              })}
            </dd>
          ) : null}
          {!reviews && !published ? <dd>{t('planner.shelves.noSignal')}</dd> : null}
        </dl>
      )}

      {course.unlocks.count > 0 && !isMandatory ? (
        <p className="flex items-center gap-1.5 text-[11px] text-[var(--color-text-muted)]">
          <KeyRound className="h-3 w-3 shrink-0" />
          {t('planner.shelves.opens', { count: course.unlocks.count })}
        </p>
      ) : null}

      {course.readiness ? (
        <p className="flex items-start gap-1.5 text-[11px] text-[var(--color-warning)]">
          <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
          {t('planner.shelves.readiness', {
            course: course.readiness.weakestPrerequisiteCourse,
            grade: course.readiness.weakestPrerequisiteGrade,
          })}
        </p>
      ) : null}

      {course.requiresManualRegistration ? (
        <p className="flex items-start gap-1.5 text-[11px] text-[var(--color-warning)]">
          <Mail className="mt-0.5 h-3 w-3 shrink-0" />
          {t('planner.shelves.manualRegistration')}
        </p>
      ) : null}

      {course.retakeClashesWithDraft ? (
        <p className="flex items-start gap-1.5 text-[11px] text-[var(--color-text-muted)]">
          <Repeat className="mt-0.5 h-3 w-3 shrink-0" />
          {t('planner.shelves.retakeClash')}
        </p>
      ) : null}

      {!course.catalogKnown ? (
        <p className="text-[11px] text-[var(--color-warning)]">
          {t('planner.shelves.notInCatalog')}
        </p>
      ) : null}

      <footer className="mt-auto flex items-center gap-1 pt-1">
        <Button
          type="button"
          size="sm"
          className="!h-8 flex-1 !px-2"
          disabled={alreadyInPlan || !course.offeredThisTerm}
          onClick={() => onAdd(course)}
        >
          <Plus className="h-4 w-4" />
          {t('planner.shelves.add')}
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="!h-8 !w-8 !p-0"
          aria-label={t('planner.courseInfo')}
          onClick={() => onInfo(course.courseNumber)}
        >
          <Info className="h-4 w-4" />
        </Button>
      </footer>
    </article>
  )
}
