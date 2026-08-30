import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { LayoutGrid } from 'lucide-react'
import type { ShelfCourse } from '../../types/api'
import type { Locale } from '../../i18n/types'
import { useTranslation } from '../../i18n'
import { plansApi } from '../../api/endpoints'
import { cn } from '../../lib/utils'
import { Card, Spinner } from '../ui/Card'
import { CourseShelfRow } from './CourseShelfRow'
import { DraftSummaryBar } from './DraftSummaryBar'

type CourseShelvesPanelProps = {
  semesterCode: string
  locale: Locale
  plannedCourses: Array<{ courseNumber?: string | null; isActive?: boolean }>
  onAdd: (course: ShelfCourse) => void
  onInfo: (courseNumber: string) => void
}

/**
 * Candidate courses grouped by the requirement each would advance.
 *
 * The rows come from the student's own outstanding requirements, so this is a
 * different thing from the auto-planner: nothing here is chosen for them, and
 * every row states what it would count toward.
 */
export function CourseShelvesPanel({
  semesterCode,
  locale,
  plannedCourses,
  onAdd,
  onInfo,
}: CourseShelvesPanelProps) {
  const { t } = useTranslation()

  const activePlanned = plannedCourses.filter(
    (course) => course.isActive !== false && course.courseNumber,
  )
  // The draft is part of the request: it decides what clashes, what is already
  // claimed, and what the summary describes.
  const plannedKey = activePlanned
    .map((course) => String(course.courseNumber))
    .sort()
    .join(',')

  const shelvesQuery = useQuery({
    queryKey: ['course-shelves', semesterCode, plannedKey],
    queryFn: () =>
      plansApi.courseShelves({
        semesterCode,
        existingPlannedCourses: activePlanned.map((course) => ({
          courseNumber: String(course.courseNumber),
          isActive: true,
        })),
      }),
    enabled: Boolean(semesterCode),
    // The draft is part of the key, so adding a course starts a NEW query.
    // Without this the whole panel — every row, every card, every row's scroll
    // position — was replaced by a spinner for the ~2.5s the refetch took, so
    // the primary action destroyed the context the student was browsing.
    placeholderData: keepPreviousData,
  })

  const plannedCourseNumbers = new Set(
    activePlanned.map((course) => String(course.courseNumber)),
  )

  return (
    <Card className="print:hidden" data-testid="course-shelves-panel">
      <h2 className="mb-1 flex items-center gap-2 text-sm font-semibold">
        <LayoutGrid className="h-4 w-4 text-[var(--color-primary)]" />
        {t('planner.shelves.title')}
      </h2>
      <p className="mb-4 flex items-center gap-2 text-xs text-[var(--color-text-muted)]">
        {t('planner.shelves.hint')}
        {/* The rows stay on screen while they refresh; this is the only sign
            that they are catching up with the draft. */}
        {shelvesQuery.isFetching && !shelvesQuery.isPending ? (
          <span className="text-[var(--color-primary)]">{t('planner.shelves.updating')}</span>
        ) : null}
      </p>

      {!semesterCode ? (
        <p className="rounded-xl border border-dashed border-[var(--color-border)] px-4 py-8 text-center text-sm text-[var(--color-text-muted)]">
          {t('planner.selectSemesterFirst')}
        </p>
      ) : shelvesQuery.isPending ? (
        <div className="flex justify-center py-8">
          <Spinner />
        </div>
      ) : shelvesQuery.isError ? (
        <p className="text-sm text-[var(--color-danger)]">{t('common.errorGeneric')}</p>
      ) : (
        <div
          className={cn(
            'space-y-6 transition-opacity',
            shelvesQuery.isFetching && 'opacity-60',
          )}
        >
          {shelvesQuery.data?.draftSummary ? (
            <DraftSummaryBar summary={shelvesQuery.data.draftSummary} />
          ) : null}
          {(shelvesQuery.data?.shelves ?? []).map((shelf) => (
            <CourseShelfRow
              key={shelf.shelfId}
              shelf={shelf}
              locale={locale}
              plannedCourseNumbers={plannedCourseNumbers}
              onAdd={onAdd}
              onInfo={onInfo}
            />
          ))}
        </div>
      )}
    </Card>
  )
}
