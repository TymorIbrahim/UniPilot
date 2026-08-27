import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { aiJobsApi } from '../../api/endpoints'
import { useAiJobPolling } from '../../hooks/useAiJobPolling'
import { useTranslation } from '../../i18n'
import { Button } from '../ui/Button'
import { Card, Spinner } from '../ui/Card'

type ExplainRiskAnalysisButtonProps = {
  analysisId: string
  /** Poll interval override, primarily for tests — defaults to useAiJobPolling's own default. */
  pollIntervalMs?: number
}

export function ExplainRiskAnalysisButton({ analysisId, pollIntervalMs }: ExplainRiskAnalysisButtonProps) {
  const { t } = useTranslation()
  const [jobId, setJobId] = useState<string | null>(null)

  const createMutation = useMutation({
    mutationFn: () => aiJobsApi.create('academic_risk_narrative', analysisId),
    onSuccess: (data) => setJobId(data.aiJob.id),
  })

  const pollQuery = useAiJobPolling(
    jobId,
    pollIntervalMs === undefined ? undefined : { intervalMs: pollIntervalMs },
  )
  const job = pollQuery.data?.aiJob
  const polling = jobId !== null

  const createError = createMutation.isError ? (createMutation.error as Error).message : null
  const pollError = pollQuery.isError ? (pollQuery.error as Error).message : null
  const jobError = job?.status === 'failed' ? job.error?.message : null
  const displayError = createError || pollError || jobError

  const inFlight = polling
    ? !displayError && (!job || job.status === 'pending' || job.status === 'processing')
    : createMutation.isPending

  const handleClick = () => {
    setJobId(null)
    createMutation.reset()
    createMutation.mutate()
  }

  return (
    <div>
      <Button
        type="button"
        variant="secondary"
        disabled={inFlight}
        onClick={handleClick}
        data-testid="explain-risk-button"
      >
        {displayError ? t('risks.tryAgain') : t('risks.explain')}
      </Button>

      {inFlight ? (
        <div
          className="mt-3 flex items-center gap-2 text-sm text-[var(--color-text-muted)]"
          data-testid="explain-risk-status"
        >
          <Spinner className="h-4 w-4" />
          {job?.status === 'processing'
            ? t('risks.explainingStatusProcessing')
            : t('risks.explainingStatusPending')}
        </div>
      ) : null}

      {displayError ? (
        <p className="mt-3 text-sm text-[var(--color-danger)]" data-testid="explain-risk-error">
          {displayError}
        </p>
      ) : null}

      {job?.status === 'completed' && job.result ? (
        <Card className="mt-3 border-[var(--color-primary)]/20" data-testid="explain-risk-narrative">
          <p className="text-xs font-medium uppercase tracking-wide text-[var(--color-primary)]">
            {t('risks.narrativeTitle')}
          </p>
          <p className="mt-2 text-sm">{job.result.narrative}</p>
        </Card>
      ) : null}
    </div>
  )
}
