import type { CourseShelf } from '../types/api'

type Translate = (key: string, params?: Record<string, string | number>) => string

/** Technion terms, in the order they run inside an academic year. */
const TERM_KEYS: Record<number, string> = {
  200: 'planner.shelves.term.winter',
  201: 'planner.shelves.term.spring',
  202: 'planner.shelves.term.summer',
}

/** "Winter 2027" — a date reads far better than "3 terms away". */
export function semesterLabel(
  offering: { academicYear: number; semesterCode: number },
  t: Translate,
): string {
  const key = TERM_KEYS[offering.semesterCode]
  const term = key ? t(key) : String(offering.semesterCode)
  return `${term} ${offering.academicYear}`
}

/**
 * How many candidates the row dropped, and why.
 *
 * Reported rather than hidden: over half of curated rows show two courses or
 * fewer, and a row that silently shrank from eleven to three reads as a thin
 * catalog rather than as a filtered one.
 */
export function filteredCount(shelf: CourseShelf): number {
  return (
    shelf.notOfferedCount +
    shelf.ineligibleCount +
    shelf.noAdditionalCreditCount +
    shelf.conflictsWithDraftCount +
    shelf.wrongDegreeLevelCount
  )
}

/**
 * The requirement's own name, translated where the catalog offers no Hebrew.
 *
 * Requirement titles exist in English only — there is no Hebrew field anywhere
 * in `degree_requirements` — which leaves English headings in an otherwise
 * Hebrew page. The bucket SUFFIXES are standardised across programs, though
 * (`physical-education` and `enrichment` appear in 61 of them), so the common
 * ones translate cleanly.
 *
 * Anything else keeps the catalog's own wording: a program-specific pool like
 * "IS focus chain (Chain B)" is a name, and guessing at a translation for it
 * would be worse than leaving it as the faculty wrote it.
 */
export function shelfTitle(shelf: CourseShelf, t: Translate): string {
  const suffix = shelf.shelfId.includes(':') ? shelf.shelfId.split(':').slice(1).join(':') : ''
  const translated = suffix ? t(`planner.shelves.requirement.${suffix}`) : ''
  // `t` echoes the key back when there is no entry for it.
  return translated && !translated.startsWith('planner.shelves.requirement.')
    ? translated
    : shelf.title
}

/** The header line for a row, which differs by what the row is asking. */
export function shelfKindLabel(kind: CourseShelf['kind'], t: Translate): string {
  if (kind === 'mandatory') return t('planner.shelves.mustTake')
  if (kind === 'open') return t('planner.shelves.anythingCounts')
  return t('planner.shelves.choose')
}
