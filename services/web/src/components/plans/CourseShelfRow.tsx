import { useState } from 'react'
import { ChevronDown } from 'lucide-react'
import type { CourseShelf, ShelfCourse } from '../../types/api'
import type { Locale } from '../../i18n/types'
import { useTranslation } from '../../i18n'
import { cn, formatCredits } from '../../lib/utils'
import { filteredCount, semesterLabel, shelfKindLabel, shelfTitle } from '../../lib/shelves'
import { ShelfCourseCard } from './ShelfCourseCard'

type CourseShelfRowProps = {
  shelf: CourseShelf
  locale: Locale
  plannedCourseNumbers: Set<string>
  onAdd: (course: ShelfCourse) => void
  onInfo: (courseNumber: string) => void
}

/**
 * One requirement, one row.
 *
 * Rows scroll horizontally rather than wrapping, so a row with three courses
 * and a row with twenty-four occupy the same vertical space and the page stays
 * scannable — the requirement names are the thing being scanned.
 *
 * An empty row is never rendered blank. Over half of curated rows surface two
 * courses or fewer, almost entirely because pool courses do not run every term,
 * so the row states its reason and still lists what is coming later.
 */
export function CourseShelfRow({
  shelf,
  locale,
  plannedCourseNumbers,
  onAdd,
  onInfo,
}: CourseShelfRowProps) {
  const { t } = useTranslation()
  const [laterOpen, setLaterOpen] = useState(false)
  const filtered = filteredCount(shelf)

  return (
    <section className="space-y-2" data-testid={`shelf-${shelf.shelfId}`}>
      <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h3 className="text-sm font-semibold text-[var(--color-text)]">{shelfTitle(shelf, t)}</h3>
        <span
          className={cn(
            'rounded-full px-2 py-0.5 text-[10px] font-medium',
            shelf.kind === 'mandatory'
              ? 'bg-[var(--color-warning)]/15 text-[var(--color-warning)]'
              : 'bg-[var(--color-border)] text-[var(--color-text-muted)]',
          )}
        >
          {shelfKindLabel(shelf.kind, t)}
        </span>
        {shelf.creditsRemaining > 0 ? (
          <span className="text-xs tabular-nums text-[var(--color-text-muted)]">
            {t('planner.shelves.creditsLeft', {
              credits: formatCredits(shelf.creditsRemaining),
            })}
          </span>
        ) : null}
        {shelf.poolSize > 0 && shelf.startedCount > 0 ? (
          <span className="text-xs text-[var(--color-primary)]">
            {t('planner.shelves.takenOf', {
              taken: shelf.startedCount,
              total: shelf.poolSize,
            })}
          </span>
        ) : null}
        {shelf.courses.length > 0 && filtered > 0 ? (
          <span
            className="text-xs text-[var(--color-text-muted)]"
            title={t('planner.shelves.filteredDetail', {
              notOffered: shelf.notOfferedCount,
              ineligible: shelf.ineligibleCount,
              noCredit: shelf.noAdditionalCreditCount,
              clash: shelf.conflictsWithDraftCount,
            })}
          >
            {t('planner.shelves.showing', {
              shown: shelf.courses.length,
              total: shelf.candidateCount,
            })}
          </span>
        ) : null}
      </header>

      {shelf.courses.length > 0 ? (
        <div className="flex gap-3 overflow-x-auto pb-2">
          {shelf.courses.map((course) => (
            <ShelfCourseCard
              key={course.courseNumber}
              course={course}
              kind={shelf.kind}
              locale={locale}
              alreadyInPlan={plannedCourseNumbers.has(course.courseNumber)}
              onAdd={onAdd}
              onInfo={onInfo}
            />
          ))}
        </div>
      ) : shelf.emptyReason ? (
        <p className="rounded-xl border border-dashed border-[var(--color-border)] px-4 py-4 text-sm text-[var(--color-text-muted)]">
          {t(
            `planner.shelves.empty.${shelf.emptyReason}` as 'planner.shelves.empty.pool_exhausted',
          )}
        </p>
      ) : null}

      {shelf.laterCourses.length > 0 ? (
        <div>
          <button
            type="button"
            onClick={() => setLaterOpen((open) => !open)}
            className="flex items-center gap-1 text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
            aria-expanded={laterOpen}
          >
            <ChevronDown
              className={cn('h-3 w-3 transition-transform', laterOpen && 'rotate-180')}
            />
            {t('planner.shelves.laterHeading', { count: shelf.laterCourses.length })}
          </button>
          {laterOpen ? (
            <ul className="mt-2 space-y-1">
              {shelf.laterCourses.map((course) => (
                <li
                  key={course.courseNumber}
                  className="flex flex-wrap items-baseline gap-x-2 rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-xs"
                >
                  <span className="font-mono text-[11px] text-[var(--color-text-muted)]">
                    {course.courseNumber}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-[var(--color-text)]">
                    {course.title}
                  </span>
                  <span className="text-[11px] text-[var(--color-text-muted)]">
                    {course.nextOffering
                      ? t('planner.shelves.nextRuns', {
                          term: semesterLabel(course.nextOffering, t),
                        })
                      : t('planner.shelves.nextUnknown')}
                  </span>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </section>
  )
}
