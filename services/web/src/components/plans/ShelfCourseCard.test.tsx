import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ShelfCourse } from '../../types/api'
import { I18nProvider } from '../../i18n'
import { ShelfCourseCard } from './ShelfCourseCard'

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

function renderCard(value: ShelfCourse, kind: 'mandatory' | 'pool' | 'open' = 'pool') {
  render(
    <I18nProvider>
      <ShelfCourseCard
        course={value}
        kind={kind}
        locale="en"
        alreadyInPlan={false}
        onAdd={vi.fn()}
        onInfo={vi.fn()}
      />
    </I18nProvider>,
  )
}

describe('ShelfCourseCard', () => {
  beforeEach(() => {
    localStorage.setItem('unipilot_locale', 'en')
  })

  it('leads a mandatory card with the cost of postponing, not with reviews', () => {
    renderCard(
      course({
        signal: {
          courseNumber: '00940111',
          reviews: { responseCount: 40, meanGeneralRank: 4.2, meanDifficultyRank: 3, scaleMax: 5 },
        },
        deferral: {
          offeredOncePerYear: true,
          nextOffering: { academicYear: 2027, semesterCode: 200 },
          termsUntilNextOffering: 3,
          dependentCount: 2,
          dependentCourseNumbers: ['00940222', '00940333'],
          dependentCountIsLowerBound: true,
        },
      }),
      'mandatory',
    )

    expect(screen.getByText(/Next runs Winter 2027/i)).toBeInTheDocument()
    expect(screen.getByText(/Gates 2 courses/i)).toBeInTheDocument()
    expect(screen.queryByText(/4\.2\/5/)).not.toBeInTheDocument()
  })

  it('leads a choice card with what students scored and thought', () => {
    renderCard(
      course({
        signal: {
          courseNumber: '00940111',
          reviews: { responseCount: 69, meanGeneralRank: 4.4, meanDifficultyRank: 3, scaleMax: 5 },
          published: {
            termCount: 4,
            students: 800,
            passRate: 0.92,
            minGrade: 10,
            maxGrade: 100,
            averageGrade: 81.4,
            medianOfTermMedians: 84,
          },
        },
      }),
    )

    expect(screen.getByText(/4\.4\/5 from 69 reviews/i)).toBeInTheDocument()
    expect(screen.getByText(/92% pass/i)).toBeInTheDocument()
  })

  it('says plainly when there is nothing to report', () => {
    renderCard(course())

    expect(screen.getByText(/no reviews or grade data yet/i)).toBeInTheDocument()
  })

  it('warns when the student barely passed the prerequisite', () => {
    renderCard(
      course({ readiness: { weakestPrerequisiteCourse: '00960411', weakestPrerequisiteGrade: 57 } }),
    )

    expect(screen.getByText(/passed its prerequisite 00960411 with 57/i)).toBeInTheDocument()
  })

  it('flags a course that cannot be enrolled through the normal system', () => {
    renderCard(course({ requiresManualRegistration: true }))

    expect(screen.getByText(/manual registration/i)).toBeInTheDocument()
  })

  it('shows why the course ranked where it did', () => {
    renderCard(course({ reasons: ['closes_requirement', 'offered_once_a_year'] }))

    expect(screen.getByText(/finishes this requirement/i)).toBeInTheDocument()
    expect(screen.getByText(/runs once a year/i)).toBeInTheDocument()
  })

  it('cannot be added when the catalog does not carry it', () => {
    renderCard(course({ catalogKnown: false, offeredThisTerm: false }), 'mandatory')

    expect(screen.getByText(/not in the course catalog/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^add$/i })).toBeDisabled()
  })
})
