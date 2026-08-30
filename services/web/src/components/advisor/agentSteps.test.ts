import { describe, expect, it } from 'vitest'
import { applyAgentStep, completeRunningSteps, isAgentStep, stepFromProgressPhrase, type AgentStep } from './agentSteps'

const thinking: AgentStep = {
  id: '1-thinking',
  kind: 'thinking',
  label: 'Thinking…',
  status: 'running',
}

const find: AgentStep = {
  id: '1-0-find',
  kind: 'find',
  label: 'Looking up your records…',
  status: 'running',
}

describe('applyAgentStep', () => {
  it('appends a new step rather than replacing the trace', () => {
    const next = applyAgentStep([thinking], find)
    expect(next).toEqual([thinking, find])
  })

  it('updates an existing step in place when the id matches', () => {
    const next = applyAgentStep([thinking, find], { ...find, status: 'done' })
    expect(next).toEqual([thinking, { ...find, status: 'done' }])
  })
})

describe('isAgentStep', () => {
  it('accepts a well-formed step event payload', () => {
    expect(isAgentStep(find)).toBe(true)
  })

  it('rejects a progress-only payload', () => {
    expect(isAgentStep({ type: 'progress', text: 'Looking up your records…' })).toBe(false)
  })
})

describe('stepFromProgressPhrase', () => {
  it('accumulates successive phrases so earlier work stays visible', () => {
    const first = stepFromProgressPhrase('Looking up your records…', [])
    const second = stepFromProgressPhrase('Working through the details…', first)
    expect(second.map((step) => step.label)).toEqual([
      'Looking up your records…',
      'Working through the details…',
    ])
    expect(second[0].status).toBe('done')
    expect(second[1].status).toBe('running')
  })

  it('does not duplicate the same phrase reported twice in a row', () => {
    const first = stepFromProgressPhrase('Thinking…', [])
    const again = stepFromProgressPhrase('Thinking…', first)
    expect(again).toHaveLength(1)
    expect(again[0].status).toBe('running')
  })
})

describe('completeRunningSteps', () => {
  it('marks running steps done without dropping earlier rows', () => {
    expect(completeRunningSteps([thinking, find])).toEqual([
      { ...thinking, status: 'done' },
      { ...find, status: 'done' },
    ])
  })
})

