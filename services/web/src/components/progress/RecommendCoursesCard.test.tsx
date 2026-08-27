import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as endpoints from '../../api/endpoints'
import { ApiError } from '../../lib/api'
import { I18nProvider } from '../../i18n'
import { RecommendCoursesCard } from './RecommendCoursesCard'

vi.mock('../../api/endpoints', () => ({
  aiJobsApi: {
    create: vi.fn(),
    get: vi.fn(),
  },
}))

function renderWithProviders() {
  localStorage.setItem('unipilot_locale', 'en')
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <I18nProvider>
      <QueryClientProvider client={queryClient}>
        <RecommendCoursesCard pollIntervalMs={10} />
      </QueryClientProvider>
    </I18nProvider>,
  )
}

function baseJob(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: 'job-1',
    jobType: 'course_recommendation_narrative',
    status: 'pending',
    input: {},
    result: null,
    error: null,
    attempts: 0,
    queuedAt: '2025-01-01T00:00:00Z',
    startedAt: null,
    completedAt: null,
    createdAt: '2025-01-01T00:00:00Z',
    updatedAt: '2025-01-01T00:00:00Z',
    ...overrides,
  }
}

describe('RecommendCoursesCard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  it('shows a status message while the job is pending, then renders the narrative once completed', async () => {
    const user = userEvent.setup()
    vi.mocked(endpoints.aiJobsApi.create).mockResolvedValue({ aiJob: baseJob() })

    let resolveFirstPoll: (value: { aiJob: ReturnType<typeof baseJob> }) => void = () => {}
    const firstPoll = new Promise<{ aiJob: ReturnType<typeof baseJob> }>((resolve) => {
      resolveFirstPoll = resolve
    })
    vi.mocked(endpoints.aiJobsApi.get)
      .mockReturnValueOnce(firstPoll)
      .mockResolvedValue({
        aiJob: baseJob({
          status: 'completed',
          result: { narrative: 'Take Algebra next.', stats: {} },
        }),
      })

    renderWithProviders()

    await user.click(screen.getByTestId('recommend-courses-button'))

    await waitFor(() =>
      expect(endpoints.aiJobsApi.create).toHaveBeenCalledWith('course_recommendation_narrative'),
    )
    expect(await screen.findByTestId('recommend-courses-status')).toBeInTheDocument()
    expect(screen.getByTestId('recommend-courses-button')).toBeDisabled()

    resolveFirstPoll({ aiJob: baseJob({ status: 'pending' }) })

    const narrative = await screen.findByTestId('recommend-courses-narrative')
    expect(narrative).toHaveTextContent('Take Algebra next.')
    expect(screen.queryByTestId('recommend-courses-status')).not.toBeInTheDocument()
  })

  it('shows an error and allows retry when the job itself fails', async () => {
    const user = userEvent.setup()
    vi.mocked(endpoints.aiJobsApi.create).mockResolvedValue({ aiJob: baseJob() })
    vi.mocked(endpoints.aiJobsApi.get).mockResolvedValue({
      aiJob: baseJob({ status: 'failed', error: { code: 'timeout', message: 'AI service timed out' } }),
    })

    renderWithProviders()
    await user.click(screen.getByTestId('recommend-courses-button'))

    const error = await screen.findByTestId('recommend-courses-error')
    expect(error).toHaveTextContent('AI service timed out')
    expect(screen.getByTestId('recommend-courses-button')).toHaveTextContent('Try again')
    expect(screen.queryByTestId('recommend-courses-status')).not.toBeInTheDocument()
  })

  it('shows an error when enqueueing itself fails (e.g. 404 no profile) without ever polling', async () => {
    const user = userEvent.setup()
    vi.mocked(endpoints.aiJobsApi.create).mockRejectedValue(
      new ApiError('Student profile not found', 404),
    )

    renderWithProviders()
    await user.click(screen.getByTestId('recommend-courses-button'))

    const error = await screen.findByTestId('recommend-courses-error')
    expect(error).toHaveTextContent('Student profile not found')
    expect(endpoints.aiJobsApi.get).not.toHaveBeenCalled()
  })
})
