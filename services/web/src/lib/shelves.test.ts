import { describe, expect, it } from 'vitest'
import type { CourseShelf } from '../types/api'
import { shelfTitle } from './shelves'

/** `t` echoes the key back when the locale has no entry, as the real one does. */
const t = (key: string) =>
  ({
    'planner.shelves.requirement.enrichment': 'העשרה אוניברסיטאית',
    'planner.shelves.requirement.elective-faculty': 'בחירה פקולטית',
  })[key] ?? key

function shelf(shelfId: string, title: string): CourseShelf {
  return {
    shelfId,
    title,
    kind: 'pool',
    requirementGroupId: 'g',
    requirementTitle: title,
    creditsRemaining: 3,
    isChoice: true,
    startedCount: 0,
    poolSize: 0,
    courses: [],
    laterCourses: [],
    candidateCount: 0,
    notOfferedCount: 0,
    ineligibleCount: 0,
    noAdditionalCreditCount: 0,
    conflictsWithDraftCount: 0,
    wrongDegreeLevelCount: 0,
    emptyReason: null,
  }
}

describe('shelfTitle', () => {
  it('translates the standardised requirement buckets', () => {
    expect(shelfTitle(shelf('009118-1-000:enrichment', 'University enrichment'), t)).toBe(
      'העשרה אוניברסיטאית',
    )
  })

  it('keeps a program-specific pool name as the faculty wrote it', () => {
    // Guessing a translation for "IS focus chain (Chain B)" would be worse
    // than leaving a name alone.
    expect(
      shelfTitle(shelf('009118-1-000:is-focus-chain-ml', 'IS focus chain (Chain B)'), t),
    ).toBe('IS focus chain (Chain B)')
  })

  it('falls back to the catalog title when the key is missing', () => {
    expect(shelfTitle(shelf('009118-1-000:something-new', 'Something new'), t)).toBe(
      'Something new',
    )
  })

  it('handles a shelf id with no program prefix', () => {
    expect(shelfTitle(shelf('enrichment', 'University enrichment'), t)).toBe(
      'University enrichment',
    )
  })
})
