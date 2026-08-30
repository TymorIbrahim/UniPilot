import { screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { advisorApi } from '../api/endpoints'
import { AdvisorPage } from './AdvisorPage'

vi.mock('../api/endpoints', () => ({
  advisorApi: {
    ask: vi.fn(),
    askStream: vi.fn(),
  },
}))

/**
 * Step-timeline coverage lives here rather than in AdvisorPage.test.tsx so the
 * existing progress/chunk/final cases stay focused on transport. This file
 * proves the Cursor-style accumulating activity list.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { render } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { I18nProvider } from '../i18n'

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <MemoryRouter>
          <AdvisorPage />
        </MemoryRouter>
      </I18nProvider>
    </QueryClientProvider>,
  )
}

function gatedStream(before: string[], after: string[]) {
  const encoder = new TextEncoder()
  const queue = [...before]
  let release: () => void = () => {}
  const gate = new Promise<void>((resolve) => {
    release = resolve
  })
  let opened = false
  const response = {
    ok: true,
    body: {
      getReader: () => ({
        read: async () => {
          if (!queue.length && !opened) {
            await gate
            opened = true
            queue.push(...after)
          }
          return queue.length
            ? { value: encoder.encode(queue.shift()), done: false }
            : { value: undefined, done: true }
        },
      }),
    },
  } as unknown as Response
  return { response, release: () => release() }
}

const ADVISOR_REPLY = {
  question: 'How many credits do I have left?',
  answer: 'You have 12.5 credits remaining.',
  confidence: 'high',
  courseIds: [] as string[],
  courses: [] as { id: string; name: string }[],
  wikiSlugs: [] as string[],
  sources: [] as string[],
  contacts: [] as string[],
  eligibility: null,
  semesterResolution: null,
  retrievalStatus: 'succeeded',
}

const CHUNK_EVENT = `data: ${JSON.stringify({ type: 'chunk', text: ADVISOR_REPLY.answer })}\n\n`
const FINAL_EVENT = `data: ${JSON.stringify({ type: 'final', data: { advisor: ADVISOR_REPLY } })}\n\n`
const stepEvent = (step: {
  id: string
  kind: string
  label: string
  status: 'running' | 'done'
}) => `data: ${JSON.stringify({ type: 'step', ...step })}\n\n`

async function ask() {
  const user = userEvent.setup()
  renderPage()
  await user.type(screen.getByTestId('advisor-input'), 'How many credits do I have left?')
  await user.click(screen.getByTestId('advisor-submit'))
}

describe('AdvisorPage activity trace', () => {
  beforeEach(() => {
    localStorage.setItem('unipilot_locale', 'en')
    vi.mocked(advisorApi.askStream).mockReset()
  })

  it('keeps earlier steps visible when a later step arrives', async () => {
    const { response, release } = gatedStream(
      [
        stepEvent({
          id: '1-thinking',
          kind: 'thinking',
          label: 'Thinking…',
          status: 'done',
        }),
        stepEvent({
          id: '1-0-find',
          kind: 'find',
          label: 'Looking up your records…',
          status: 'running',
        }),
      ],
      [CHUNK_EVENT, FINAL_EVENT],
    )
    vi.mocked(advisorApi.askStream).mockResolvedValue(response)

    await ask()

    const activity = await screen.findByTestId('advisor-activity')
    expect(activity).toHaveTextContent('Thinking')
    expect(activity).toHaveTextContent('Looking up your records')
    expect(screen.queryByText(ADVISOR_REPLY.answer)).not.toBeInTheDocument()

    release()

    expect(await screen.findByText(ADVISOR_REPLY.answer)).toBeInTheDocument()
    expect(screen.getByTestId('advisor-activity-toggle')).toBeInTheDocument()
  })
})
