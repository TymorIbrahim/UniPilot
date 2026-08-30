import { useCallback, useEffect, useRef, useState } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useTranslation } from '../../i18n'
import { cn } from '../../lib/utils'

type ShelfScrollerProps = {
  children: React.ReactNode
  label: string
}

/** How much of the row one press moves, as a fraction of what is visible. */
const PAGE_FRACTION = 0.8

/**
 * A horizontally scrolling row with the affordance that makes it obvious.
 *
 * Wide rows scroll, but nothing on screen said so: the fourteenth course in a
 * row was reachable and invisible. The arrows appear only when the row actually
 * overflows and each one hides at its end, so a row of three courses carries no
 * furniture it does not need.
 *
 * Direction matters here. In RTL the content starts at the right and
 * `scrollLeft` runs negative, so a fixed positive delta would scroll the wrong
 * way and the arrow that looks like "forward" would go back. The delta is
 * signed by the document direction and the arrow glyphs are swapped with it.
 */
export function ShelfScroller({ children, label }: ShelfScrollerProps) {
  const { t, dir } = useTranslation()
  const ref = useRef<HTMLDivElement>(null)
  const [atStart, setAtStart] = useState(true)
  const [atEnd, setAtEnd] = useState(true)

  const measure = useCallback(() => {
    const el = ref.current
    if (!el) return
    const overflow = el.scrollWidth - el.clientWidth
    if (overflow <= 1) {
      setAtStart(true)
      setAtEnd(true)
      return
    }
    // Normalised so both directions read as 0 -> overflow.
    const travelled = Math.abs(el.scrollLeft)
    setAtStart(travelled <= 1)
    setAtEnd(travelled >= overflow - 1)
  }, [])

  useEffect(() => {
    measure()
    const el = ref.current
    if (!el) return
    const observer = new ResizeObserver(measure)
    observer.observe(el)
    return () => observer.disconnect()
  }, [measure, children])

  const scrollBy = (forward: boolean) => {
    const el = ref.current
    if (!el) return
    const distance = Math.max(240, el.clientWidth * PAGE_FRACTION)
    const towardsEnd = dir === 'rtl' ? -distance : distance
    el.scrollBy({ left: forward ? towardsEnd : -towardsEnd, behavior: 'smooth' })
  }

  const hidden = atStart && atEnd

  return (
    <div className="group relative">
      <div
        ref={ref}
        onScroll={measure}
        className="flex gap-3 overflow-x-auto pb-2 scroll-smooth"
        role="group"
        aria-label={label}
        tabIndex={0}
      >
        {children}
      </div>

      {hidden ? null : (
        <>
          <ShelfArrow
            side="start"
            dir={dir}
            disabled={atStart}
            label={t('planner.shelves.scrollBack')}
            onClick={() => scrollBy(false)}
          />
          <ShelfArrow
            side="end"
            dir={dir}
            disabled={atEnd}
            label={t('planner.shelves.scrollForward')}
            onClick={() => scrollBy(true)}
          />
        </>
      )}
    </div>
  )
}

function ShelfArrow({
  side,
  dir,
  disabled,
  label,
  onClick,
}: {
  side: 'start' | 'end'
  dir: 'rtl' | 'ltr'
  disabled: boolean
  label: string
  onClick: () => void
}) {
  // "start" is the right-hand edge in RTL, and the glyph must follow.
  const onLeftEdge = (side === 'start') === (dir === 'ltr')
  const Icon = onLeftEdge ? ChevronLeft : ChevronRight

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      className={cn(
        'absolute top-1/2 z-10 hidden -translate-y-1/2 rounded-full border border-[var(--color-border)]',
        'bg-white/95 p-1.5 shadow-sm transition md:block',
        // Visible at rest, not only on hover: this is the one cue that the row
        // continues, and a student who has not met the pattern before will not
        // hover a row to find out.
        'opacity-60 hover:bg-white hover:opacity-100 focus-visible:opacity-100',
        'group-hover:opacity-100',
        'disabled:pointer-events-none disabled:opacity-0',
        onLeftEdge ? '-left-1' : '-right-1',
      )}
    >
      <Icon className="h-4 w-4 text-[var(--color-text)]" />
    </button>
  )
}
