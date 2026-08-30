import { useEffect, useState } from 'react'
import { Check, ChevronDown, LoaderCircle } from 'lucide-react'
import { useTranslation } from '../../i18n'
import type { AgentStep } from './agentSteps'

const KIND_KEYS: Record<string, string> = {
  thinking: 'advisor.step.thinking',
  find: 'advisor.step.find',
  search_corpus: 'advisor.step.search',
  interpret: 'advisor.step.interpret',
  compute: 'advisor.step.compute',
  traverse: 'advisor.step.traverse',
  forecast: 'advisor.step.forecast',
  optimize: 'advisor.step.optimize',
  propose: 'advisor.step.propose',
}

function labelFor(step: AgentStep, t: (key: string, params?: Record<string, string | number>) => string) {
  const key = KIND_KEYS[step.kind]
  if (!key) return step.label
  const translated = t(key)
  return translated === key ? step.label : translated
}

/**
 * Live trace of what the advisor is doing — the Cursor / Claude Code pattern:
 * while the run is in flight the list stays open; once the answer lands it
 * collapses to a one-line summary the student can expand.
 */
export function AgentActivity({
  steps,
  isLive,
}: {
  steps: AgentStep[]
  isLive: boolean
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(isLive)

  useEffect(() => {
    setOpen(isLive)
  }, [isLive])

  if (steps.length === 0) return null

  const running = steps.find((step) => step.status === 'running')
  const summary = isLive
    ? labelFor(running ?? steps[steps.length - 1], t)
    : t('advisor.stepsSummary', { count: steps.length })

  return (
    <div className="agent-activity" data-testid="advisor-activity">
      <button
        type="button"
        className="agent-activity-toggle"
        data-testid="advisor-activity-toggle"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
      >
        {isLive ? (
          <LoaderCircle className="agent-activity-spinner" aria-hidden />
        ) : (
          <Check className="agent-activity-check" aria-hidden />
        )}
        <span dir="auto">{summary}</span>
        <ChevronDown className={`agent-activity-chevron ${open ? 'is-open' : ''}`} aria-hidden />
      </button>
      {open ? (
        <ol className="agent-activity-list" aria-live="polite">
          {steps.map((step) => (
            <li
              key={step.id}
              className={`agent-activity-step is-${step.status}`}
              data-status={step.status}
            >
              {step.status === 'running' ? (
                <LoaderCircle className="agent-activity-spinner" aria-hidden />
              ) : (
                <Check className="agent-activity-check" aria-hidden />
              )}
              <span dir="auto">{labelFor(step, t)}</span>
            </li>
          ))}
        </ol>
      ) : null}
    </div>
  )
}
