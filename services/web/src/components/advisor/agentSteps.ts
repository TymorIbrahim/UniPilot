/** One visible action the advisor took while working on a question.

 * The stream reports these as `{type: "step"}` events. Labels are student-facing
 * and must never carry a grounded number or course code -- those belong in the
 * answer, not in the activity trace.
 */
export type AgentStepStatus = 'running' | 'done'

export type AgentStep = {
  id: string
  kind: string
  label: string
  status: AgentStepStatus
}

export function isAgentStep(value: unknown): value is AgentStep {
  if (typeof value !== 'object' || value === null) return false
  const step = value as Partial<AgentStep>
  return (
    typeof step.id === 'string' &&
    step.id.length > 0 &&
    typeof step.kind === 'string' &&
    typeof step.label === 'string' &&
    (step.status === 'running' || step.status === 'done')
  )
}

/** Insert or update a step by `id`, preserving the order first seen. */
export function applyAgentStep(steps: AgentStep[], incoming: AgentStep): AgentStep[] {
  const index = steps.findIndex((step) => step.id === incoming.id)
  if (index === -1) return [...steps, incoming]
  return steps.map((step, i) => (i === index ? { ...step, ...incoming } : step))
}

/** Turn a legacy `{type: "progress", text}` event into a running step.

 * Used only when the stream has not sent any structured `step` events, so an
 * older backend still produces an accumulating trace instead of a single
 * replacing phrase.
 */
export function stepFromProgressPhrase(text: string, previous: AgentStep[]): AgentStep[] {
  const label = text.trim()
  if (!label) return previous
  const completed = previous.map((step) =>
    step.status === 'running' ? { ...step, status: 'done' as const } : step,
  )
  const last = completed[completed.length - 1]
  if (last?.label === label) {
    return completed.map((step, i) =>
      i === completed.length - 1 ? { ...step, status: 'running' } : step,
    )
  }
  return [
    ...completed,
    { id: `progress-${completed.length + 1}`, kind: 'progress', label, status: 'running' },
  ]
}

/** Mark leftover running rows done when the stream ends. */
export function completeRunningSteps(steps: AgentStep[]): AgentStep[] {
  return steps.map((step) =>
    step.status === 'running' ? { ...step, status: 'done' as const } : step,
  )
}

