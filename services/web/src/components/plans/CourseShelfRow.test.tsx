import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { CourseShelf, ShelfCourse } from '../../types/api'
import { I18nProvider } from '../../i18n'
import { CourseShelfRow } from './CourseShelfRow'

function course(overrides: Partial<ShelfCourse> = {}): ShelfCourse {
  return {
    id: 'cid',
    courseNumber: '00940111',
    title: 'Algorithms',
    credits: 3,
    offeredThisTerm: true,
    eligibility: { status: 'eligible', missingOptions: [] },
    unlocks: { count: 0, courseNumbers: [] },
    retakeClashesWithDraft: false,
    requiresManualRegistration: false,
    catalogKnown: true,
    reasons: [],
    ...overrides,
  }
}

function shelf(overrides: Partial<CourseShelf> = {}): CourseShelf {
  return {
    shelfId: 'p:chain',
    title: 'ML chain',
    kind: 'pool',
    requirementGroupId: 'p:elective',
    requirementTitle: 'Faculty electives',
    creditsRemaining: 3.5,
    isChoice: true,
    startedCount: 0,
    poolSize: 0,
    courses: [course()],
    laterCourses: [],
    candidateCount: 1,
    notOfferedCount: 0,
    ineligibleCount: 0,
    noAdditionalCreditCount: 0,
    conflictsWithDraftCount: 0,
    wrongDegreeLevelCount: 0,
    emptyReason: null,
    ...overrides,
  }
}

function renderRow(value: CourseShelf, onAdd = vi.fn()) {
  render(
    <I18nProvider>
      <CourseShelfRow
        shelf={value}
        locale="en"
        plannedCourseNumbers={new Set()}
        onAdd={onAdd}
        onInfo={vi.fn()}
      />
    </I18nProvider>,
  )
  return onAdd
}

describe('CourseShelfRow', () => {
  beforeEach(() => {
    localStorage.setItem('unipilot_locale', 'en')
  })

  it('names the requirement and what is left of it', () => {
    renderRow(shelf())

    expect(screen.getByText('ML chain')).toBeInTheDocument()
    expect(screen.getByText(/3\.5 credits left/i)).toBeInTheDocument()
  })

  it('marks a mandatory row differently from a menu', () => {
    renderRow(shelf({ kind: 'mandatory', isChoice: false }))

    expect(screen.getByText(/must take/i)).toBeInTheDocument()
  })

  it('shows chain momentum when the student has started it', () => {
    renderRow(shelf({ startedCount: 3, poolSize: 19 }))

    expect(screen.getByText(/3 of 19 taken/i)).toBeInTheDocument()
  })

  it('states why an empty row is empty rather than rendering blank', () => {
    renderRow(
      shelf({ courses: [], candidateCount: 3, emptyReason: 'none_offered_this_term' }),
    )

    expect(screen.getByText(/none of these run this semester/i)).toBeInTheDocument()
  })

  it('keeps courses that do not run this term behind a disclosure', async () => {
    const user = userEvent.setup()
    renderRow(
      shelf({
        laterCourses: [
          {
            courseNumber: '00940222',
            title: 'Deep Learning',
            credits: 3,
            nextOffering: { academicYear: 2026, semesterCode: 201 },
          },
        ],
      }),
    )

    expect(screen.queryByText('Deep Learning')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /not this term/i }))

    expect(screen.getByText('Deep Learning')).toBeInTheDocument()
    expect(screen.getByText(/Spring 2026/)).toBeInTheDocument()
  })

  it('reports that the row was filtered, so a short row is not read as a thin catalog', () => {
    renderRow(shelf({ candidateCount: 11, notOfferedCount: 7, ineligibleCount: 3 }))

    expect(screen.getByText(/showing 1 of 11/i)).toBeInTheDocument()
  })

  it('adds the course it was given', async () => {
    const user = userEvent.setup()
    const onAdd = renderRow(shelf())

    await user.click(screen.getByRole('button', { name: /^add$/i }))

    expect(onAdd).toHaveBeenCalledWith(expect.objectContaining({ courseNumber: '00940111' }))
  })

  it('cannot add a course the term does not offer', () => {
    renderRow(shelf({ courses: [course({ offeredThisTerm: false })] }))

    expect(screen.getByRole('button', { name: /^add$/i })).toBeDisabled()
  })
})
