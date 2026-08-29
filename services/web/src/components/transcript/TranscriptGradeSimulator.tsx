import { useMemo, useRef, useState } from 'react'
import {
  Calculator,
  ChevronDown,
  ChevronUp,
  Pencil,
  Plus,
  RotateCcw,
  Search,
  TrendingDown,
  TrendingUp,
  X,
} from 'lucide-react'
import { useCatalogCourses } from '../../hooks/useCatalogCourses'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import { TranscriptSemesterPicker } from './TranscriptSemesterPicker'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'
import { Input } from '../ui/Input'
import { computeTranscriptStats, filterTranscriptRecords } from '../../lib/transcript'
import type { TranscriptStats } from '../../lib/transcript'
import { cn, formatCredits } from '../../lib/utils'
import type { CompletedCourse, CourseSummary } from '../../types/api'
import type { Locale } from '../../i18n/types'

type TranscriptGradeSimulatorProps = {
  records: CompletedCourse[]
  stats: TranscriptStats
  catalogYear?: number | null
  currentSemesterCode?: string | null
  locale: Locale
  t: (key: string, params?: Record<string, string | number>) => string
}

type SimulatedAdd = {
  kind: 'add'
  tempId: string
  courseNumber: string
  courseTitle: string
  semesterCode: string
  grade: number
  creditsEarned: number
}

type SimulatedOverride = {
  kind: 'override'
  tempId: string
  targetId: string
  courseNumber: string
  courseTitle: string
  originalGrade: string
  grade: number
}

type SimulatedEdit = SimulatedAdd | SimulatedOverride

let tempIdCounter = 0
function nextTempId(): string {
  tempIdCounter += 1
  return String(tempIdCounter)
}

function localizedCourseTitle(course: CourseSummary, locale: Locale): string {
  if (locale === 'he' && course.titleHebrew) return course.titleHebrew
  return course.title ?? course.titleHebrew ?? course.courseNumber
}

function applyEditsToRecords(records: CompletedCourse[], edits: SimulatedEdit[]): CompletedCourse[] {
  const overrideByTarget = new Map(
    edits
      .filter((edit): edit is SimulatedOverride => edit.kind === 'override')
      .map((edit) => [edit.targetId, edit]),
  )
  const adjusted = records.map((record) => {
    const override = overrideByTarget.get(record.id)
    if (!override) return record
    return { ...record, grade: String(override.grade), gradePoints: null }
  })
  const additions: CompletedCourse[] = edits
    .filter((edit): edit is SimulatedAdd => edit.kind === 'add')
    .map((edit) => ({
      id: `sim-${edit.tempId}`,
      courseId: `sim-${edit.tempId}`,
      courseNumber: edit.courseNumber,
      courseTitle: edit.courseTitle,
      semesterCode: edit.semesterCode,
      grade: String(edit.grade),
      creditsEarned: edit.creditsEarned,
      attempt: 1,
      source: 'manual',
    }))
  return [...adjusted, ...additions]
}

function DeltaBadge({ delta }: { delta: number }) {
  if (Math.abs(delta) < 0.05) {
    return <span className="text-xs font-medium text-[var(--color-text-muted)]">±0.0</span>
  }
  const up = delta > 0
  const Icon = up ? TrendingUp : TrendingDown
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 text-xs font-semibold',
        up ? 'text-emerald-700' : 'text-[var(--color-danger)]',
      )}
    >
      <Icon className="h-3.5 w-3.5" aria-hidden />
      {up ? '+' : ''}
      {delta.toFixed(1)}
    </span>
  )
}

export function TranscriptGradeSimulator({
  records,
  stats,
  catalogYear,
  currentSemesterCode,
  locale,
  t,
}: TranscriptGradeSimulatorProps) {
  const [expanded, setExpanded] = useState(false)
  const [edits, setEdits] = useState<SimulatedEdit[]>([])

  // -- "add a hypothetical course" sub-form --
  const searchRef = useRef<HTMLInputElement>(null)
  const [addQuery, setAddQuery] = useState('')
  const [selectedCourse, setSelectedCourse] = useState<CourseSummary | null>(null)
  const [addSemesterCode, setAddSemesterCode] = useState(currentSemesterCode ?? '')
  const [addGrade, setAddGrade] = useState('85')
  const [addCredits, setAddCredits] = useState('3')
  const [addMenuOpen, setAddMenuOpen] = useState(false)

  const debouncedAddQuery = useDebouncedValue(addQuery.trim(), 300)
  const coursesQuery = useCatalogCourses({ query: debouncedAddQuery, faculty: '' })
  const addSuggestions = useMemo(() => {
    if (!debouncedAddQuery || debouncedAddQuery.length < 2) return []
    return coursesQuery.items.slice(0, 8)
  }, [coursesQuery.items, debouncedAddQuery])

  // -- "override an existing course" sub-form --
  const [overrideQuery, setOverrideQuery] = useState('')
  const [overrideTarget, setOverrideTarget] = useState<CompletedCourse | null>(null)
  const [overrideGrade, setOverrideGrade] = useState('')
  const [overrideMenuOpen, setOverrideMenuOpen] = useState(false)

  const overrideCandidates = useMemo(() => {
    if (!overrideQuery.trim()) return []
    return filterTranscriptRecords(records, overrideQuery).slice(0, 8)
  }, [records, overrideQuery])

  const simulatedRecords = useMemo(() => applyEditsToRecords(records, edits), [records, edits])
  const simulatedStats = useMemo(() => computeTranscriptStats(simulatedRecords), [simulatedRecords])
  const delta =
    stats.averageGrade != null && simulatedStats.averageGrade != null
      ? simulatedStats.averageGrade - stats.averageGrade
      : 0

  const addEdit = () => {
    if (!selectedCourse) return
    const grade = Number(addGrade)
    const credits = Number(addCredits)
    if (!Number.isFinite(grade) || !Number.isFinite(credits) || !addSemesterCode) return
    setEdits((current) => [
      ...current,
      {
        kind: 'add',
        tempId: nextTempId(),
        courseNumber: selectedCourse.courseNumber,
        courseTitle: localizedCourseTitle(selectedCourse, locale),
        semesterCode: addSemesterCode,
        grade,
        creditsEarned: credits,
      },
    ])
    setAddQuery('')
    setSelectedCourse(null)
    setAddGrade('85')
    searchRef.current?.focus()
  }

  const applyOverride = () => {
    if (!overrideTarget) return
    const grade = Number(overrideGrade)
    if (!Number.isFinite(grade)) return
    setEdits((current) => [
      ...current.filter((edit) => !(edit.kind === 'override' && edit.targetId === overrideTarget.id)),
      {
        kind: 'override',
        tempId: nextTempId(),
        targetId: overrideTarget.id,
        courseNumber: overrideTarget.courseNumber ?? overrideTarget.courseId,
        courseTitle: overrideTarget.courseTitle ?? overrideTarget.courseNumber ?? overrideTarget.courseId,
        originalGrade: overrideTarget.grade,
        grade,
      },
    ])
    setOverrideQuery('')
    setOverrideTarget(null)
    setOverrideGrade('')
  }

  const removeEdit = (tempId: string) => {
    setEdits((current) => current.filter((edit) => edit.tempId !== tempId))
  }

  const reset = () => {
    setEdits([])
    setSelectedCourse(null)
    setOverrideTarget(null)
  }

  return (
    <Card className="overflow-hidden p-0" data-testid="transcript-grade-simulator">
      <button
        type="button"
        onClick={() => setExpanded((current) => !current)}
        className="flex w-full items-center justify-between gap-3 px-6 py-4 text-start"
        data-testid="transcript-simulator-toggle"
      >
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[var(--color-primary)]/10 text-[var(--color-primary)]">
            <Calculator className="h-4 w-4" aria-hidden />
          </div>
          <div>
            <p className="text-sm font-semibold">{t('transcript.simulator.title')}</p>
            <p className="mt-0.5 text-xs text-[var(--color-text-muted)]">{t('transcript.simulator.hint')}</p>
          </div>
        </div>
        {expanded ? (
          <ChevronUp className="h-4 w-4 shrink-0 text-[var(--color-text-muted)]" aria-hidden />
        ) : (
          <ChevronDown className="h-4 w-4 shrink-0 text-[var(--color-text-muted)]" aria-hidden />
        )}
      </button>

      {expanded ? (
        <div className="space-y-6 border-t border-[var(--color-border)] px-6 py-6">
          <div className="grid gap-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-muted)]/40 p-4 sm:grid-cols-3">
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
                {t('transcript.averageGrade')}
              </p>
              <p className="mt-1 text-lg font-semibold tabular-nums">
                {stats.averageGrade != null ? stats.averageGrade.toFixed(1) : '—'}
              </p>
            </div>
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
                {t('transcript.simulator.simulatedAverage')}
              </p>
              <p className="mt-1 text-lg font-semibold tabular-nums text-[var(--color-primary)]">
                {simulatedStats.averageGrade != null ? simulatedStats.averageGrade.toFixed(1) : '—'}
              </p>
            </div>
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
                {t('transcript.simulator.change')}
              </p>
              <p className="mt-1 text-lg font-semibold tabular-nums">
                <DeltaBadge delta={delta} />
              </p>
            </div>
          </div>

          {edits.length > 0 ? (
            <div className="space-y-2" data-testid="transcript-simulator-edits">
              <p className="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
                {t('transcript.simulator.pendingEdits', { count: edits.length })}
              </p>
              {edits.map((edit) => (
                <div
                  key={edit.tempId}
                  className="flex items-center justify-between gap-3 rounded-xl border border-[var(--color-border)] bg-white px-4 py-2.5 text-sm"
                >
                  <div className="flex min-w-0 items-center gap-2">
                    {edit.kind === 'add' ? (
                      <Plus className="h-3.5 w-3.5 shrink-0 text-emerald-600" aria-hidden />
                    ) : (
                      <Pencil className="h-3.5 w-3.5 shrink-0 text-amber-600" aria-hidden />
                    )}
                    <span className="truncate">
                      <span className="font-mono text-[var(--color-primary)]">{edit.courseNumber}</span>{' '}
                      {edit.courseTitle}
                    </span>
                    {edit.kind === 'override' ? (
                      <span className="shrink-0 text-xs text-[var(--color-text-muted)]">
                        {edit.originalGrade} → {edit.grade}
                      </span>
                    ) : (
                      <span className="shrink-0 text-xs text-[var(--color-text-muted)]">{edit.grade}</span>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={() => removeEdit(edit.tempId)}
                    className="shrink-0 rounded-full p-1 text-[var(--color-text-muted)] hover:bg-[var(--color-surface-muted)] hover:text-[var(--color-danger)]"
                    aria-label={t('transcript.simulator.removeEdit')}
                    data-testid={`transcript-simulator-remove-${edit.tempId}`}
                  >
                    <X className="h-3.5 w-3.5" aria-hidden />
                  </button>
                </div>
              ))}
              <Button type="button" variant="ghost" size="sm" onClick={reset} data-testid="transcript-simulator-reset">
                <RotateCcw className="h-3.5 w-3.5" />
                {t('transcript.simulator.resetButton')}
              </Button>
            </div>
          ) : null}

          <div className="grid gap-6 lg:grid-cols-2">
            <div className="space-y-3 rounded-xl border border-[var(--color-border)] p-4">
              <p className="text-sm font-medium">{t('transcript.simulator.addHypothetical')}</p>
              <div className="relative">
                <Search className="pointer-events-none absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--color-text-muted)]" />
                <input
                  ref={searchRef}
                  type="search"
                  value={addQuery}
                  onChange={(event) => {
                    setAddQuery(event.target.value)
                    setSelectedCourse(null)
                    setAddMenuOpen(true)
                  }}
                  onFocus={() => setAddMenuOpen(true)}
                  placeholder={t('transcript.courseSearchPlaceholder')}
                  className="h-11 w-full rounded-xl border border-[var(--color-border)] bg-white ps-10 pe-3 text-sm focus:border-[var(--color-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/15"
                  data-testid="transcript-simulator-add-search"
                />
                {addMenuOpen && addSuggestions.length > 0 && !selectedCourse ? (
                  <div className="absolute z-20 mt-2 w-full overflow-hidden rounded-xl border border-[var(--color-border)] bg-white shadow-[var(--shadow-soft)]">
                    {addSuggestions.map((course) => (
                      <button
                        key={course.courseNumber}
                        type="button"
                        className="flex w-full items-start justify-between gap-3 px-4 py-2.5 text-start text-sm hover:bg-[var(--color-surface-muted)]"
                        onClick={() => {
                          setSelectedCourse(course)
                          setAddQuery(course.courseNumber)
                          setAddMenuOpen(false)
                          if (course.credits != null) setAddCredits(String(course.credits))
                        }}
                      >
                        <span>
                          <span className="font-mono font-medium text-[var(--color-primary)]">
                            {course.courseNumber}
                          </span>
                          <span className="mt-0.5 block text-[var(--color-text)]">
                            {localizedCourseTitle(course, locale)}
                          </span>
                        </span>
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>

              <TranscriptSemesterPicker
                value={addSemesterCode}
                onChange={setAddSemesterCode}
                catalogYear={catalogYear}
                currentSemesterCode={currentSemesterCode}
              />
              <div className="grid grid-cols-2 gap-3">
                <Input
                  label={t('transcript.grade')}
                  type="number"
                  min={0}
                  max={100}
                  value={addGrade}
                  onChange={(event) => setAddGrade(event.target.value)}
                />
                <Input
                  label={t('transcript.creditsEarned')}
                  type="number"
                  step="0.5"
                  min={0}
                  value={addCredits}
                  onChange={(event) => setAddCredits(event.target.value)}
                />
              </div>
              <Button
                type="button"
                size="sm"
                variant="secondary"
                disabled={!selectedCourse}
                onClick={addEdit}
                data-testid="transcript-simulator-add-button"
              >
                <Plus className="h-3.5 w-3.5" />
                {t('transcript.simulator.addButton')}
              </Button>
            </div>

            <div className="space-y-3 rounded-xl border border-[var(--color-border)] p-4">
              <p className="text-sm font-medium">{t('transcript.simulator.overrideExisting')}</p>
              <div className="relative">
                <Search className="pointer-events-none absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--color-text-muted)]" />
                <input
                  type="search"
                  value={overrideQuery}
                  onChange={(event) => {
                    setOverrideQuery(event.target.value)
                    setOverrideTarget(null)
                    setOverrideMenuOpen(true)
                  }}
                  onFocus={() => setOverrideMenuOpen(true)}
                  placeholder={t('transcript.simulator.overrideSearchPlaceholder')}
                  className="h-11 w-full rounded-xl border border-[var(--color-border)] bg-white ps-10 pe-3 text-sm focus:border-[var(--color-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/15"
                  data-testid="transcript-simulator-override-search"
                />
                {overrideMenuOpen && overrideCandidates.length > 0 && !overrideTarget ? (
                  <div className="absolute z-20 mt-2 w-full overflow-hidden rounded-xl border border-[var(--color-border)] bg-white shadow-[var(--shadow-soft)]">
                    {overrideCandidates.map((record) => (
                      <button
                        key={record.id}
                        type="button"
                        className="flex w-full items-start justify-between gap-3 px-4 py-2.5 text-start text-sm hover:bg-[var(--color-surface-muted)]"
                        onClick={() => {
                          setOverrideTarget(record)
                          setOverrideQuery(record.courseNumber ?? record.courseTitle ?? '')
                          setOverrideMenuOpen(false)
                          setOverrideGrade(record.grade)
                        }}
                      >
                        <span>
                          <span className="font-mono font-medium text-[var(--color-primary)]">
                            {record.courseNumber}
                          </span>
                          <span className="mt-0.5 block text-[var(--color-text)]">{record.courseTitle}</span>
                        </span>
                        <span className="shrink-0 text-xs text-[var(--color-text-muted)]">{record.grade}</span>
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>

              {overrideTarget ? (
                <div className="rounded-xl border border-[var(--color-primary)]/15 bg-[var(--color-primary)]/5 px-4 py-3 text-sm">
                  <p className="font-mono text-[var(--color-primary)]">{overrideTarget.courseNumber}</p>
                  <p className="mt-0.5">{overrideTarget.courseTitle}</p>
                  <p className="mt-1 text-xs text-[var(--color-text-muted)]">
                    {t('transcript.simulator.currentGrade')}: {overrideTarget.grade} ·{' '}
                    {formatCredits(overrideTarget.creditsEarned)} {t('common.credits')}
                  </p>
                </div>
              ) : null}

              <Input
                label={t('transcript.simulator.newGrade')}
                type="number"
                min={0}
                max={100}
                value={overrideGrade}
                onChange={(event) => setOverrideGrade(event.target.value)}
                disabled={!overrideTarget}
                data-testid="transcript-simulator-new-grade"
              />
              <Button
                type="button"
                size="sm"
                variant="secondary"
                disabled={!overrideTarget || overrideGrade === ''}
                onClick={applyOverride}
                data-testid="transcript-simulator-override-button"
              >
                <Pencil className="h-3.5 w-3.5" />
                {t('transcript.simulator.applyButton')}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </Card>
  )
}
