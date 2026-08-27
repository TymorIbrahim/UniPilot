import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as endpoints from '../../api/endpoints'
import { ApiError } from '../../lib/api'
import { I18nProvider } from '../../i18n'
import { ExplainRiskAnalysisButton } from './ExplainRiskAnalysisButton'

vi.mock('../../api/endpoints', () => ({
  aiJobsApi: {
    create: vi.fn(),
    get: vi.fn(),
  },
}))

function renderWithProviders(analysisId = 'analysis-1') {
  localStorage.setItem('unipilot_locale', 'en')
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <I18nProvider>
      <QueryClientProvider client={queryClient}>
        <ExplainRiskAnalysisButton analysisId={analysisId} pollIntervalMs={10} />
      </QueryClientProvider>
    </I18nProvider>,
  )
}

function baseJob(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: 'job-1',
    jobType: 'academic_risk_narrative',
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

describe('ExplainRiskAnalysisButton', () => {
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
          result: { narrative: 'You have one low-severity risk.', stats: {} },
        }),
      })

    renderWithProviders()

    await user.click(screen.getByTestId('explain-risk-button'))

    await waitFor(() =>
      expect(endpoints.aiJobsApi.create).toHaveBeenCalledWith('academic_risk_narrative', 'analysis-1'),
    )
    // The first poll is still in flight — status should be visible and the trigger disabled.
    expect(await screen.findByTestId('explain-risk-status')).toBeInTheDocument()
    expect(screen.getByTestId('explain-risk-button')).toBeDisabled()

    resolveFirstPoll({ aiJob: baseJob({ status: 'pending' }) })

    const narrative = await screen.findByTestId('explain-risk-narrative')
    expect(narrative).toHaveTextContent('You have one low-severity risk.')
    expect(screen.queryByTestId('explain-risk-status')).not.toBeInTheDocument()
  })

  it('shows an error and allows retry when the job itself fails', async () => {
    const user = userEvent.setup()
    vi.mocked(endpoints.aiJobsApi.create).mockResolvedValue({ aiJob: baseJob() })
    vi.mocked(endpoints.aiJobsApi.get).mockResolvedValue({
      aiJob: baseJob({ status: 'failed', error: { code: 'timeout', message: 'AI service timed out' } }),
    })

    renderWithProviders()
    await user.click(screen.getByTestId('explain-risk-button'))

    const error = await screen.findByTestId('explain-risk-error')
    expect(error).toHaveTextContent('AI service timed out')
    expect(screen.getByTestId('explain-risk-button')).toHaveTextContent('Try again')
    expect(screen.queryByTestId('explain-risk-status')).not.toBeInTheDocument()
  })

  it('shows an error when enqueueing itself fails (e.g. 429/503) without ever polling', async () => {
    const user = userEvent.setup()
    vi.mocked(endpoints.aiJobsApi.create).mockRejectedValue(
      new ApiError('Too many AI job requests. Please try again later.', 429),
    )

    renderWithProviders()
    await user.click(screen.getByTestId('explain-risk-button'))

    const error = await screen.findByTestId('explain-risk-error')
    expect(error).toHaveTextContent('Too many AI job requests')
    expect(endpoints.aiJobsApi.get).not.toHaveBeenCalled()
  })
})
