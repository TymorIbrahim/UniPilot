import { useMutation } from '@tanstack/react-query'
import { AlertTriangle, GraduationCap, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { aiJobsApi } from '../../api/endpoints'
import { useAiJobPolling } from '../../hooks/useAiJobPolling'
// Uses useTranslation() internally (unlike this folder's presentational components,
// which take `t` as a prop) because it's a stateful AI-job consumer, matching
// ExplainRiskAnalysisButton rather than the pure progress subcomponents.
import { useTranslation } from '../../i18n'
import { Button } from '../ui/Button'
import { Badge, Card, Spinner } from '../ui/Card'

type RecommendCoursesCardProps = {
  /** Poll interval override, primarily for tests — defaults to useAiJobPolling's own default. */
  pollIntervalMs?: number
}

export function RecommendCoursesCard({ pollIntervalMs }: RecommendCoursesCardProps = {}) {
  const { t } = useTranslation()
  const [jobId, setJobId] = useState<string | null>(null)

  const createMutation = useMutation({
    mutationFn: () => aiJobsApi.create('course_recommendation_narrative'),
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

  const stats =
    job?.status === 'completed'
      ? (job.result?.stats as { mandatoryCount?: number; electiveCount?: number } | undefined)
      : undefined

  return (
    <Card className="border-[var(--color-primary)]/10" data-testid="recommend-courses-card">
      <div className="flex items-center justify-between gap-4">
        <h2 className="flex items-center gap-2 text-sm font-semibold">
          <GraduationCap className="h-4 w-4 text-[var(--color-primary)]" />
          {t('progress.recommendations.title')}
        </h2>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          disabled={inFlight}
          onClick={handleClick}
          data-testid="recommend-courses-button"
        >
          <Sparkles className="h-3.5 w-3.5" />
          {displayError ? t('progress.recommendations.tryAgain') : t('progress.recommendations.recommend')}
        </Button>
      </div>

      {inFlight ? (
        <div
          className="mt-3 inline-flex items-center gap-2 rounded-full bg-[var(--color-surface-muted)] px-3 py-1.5 text-sm text-[var(--color-text-muted)]"
          data-testid="recommend-courses-status"
        >
          <Spinner className="h-3.5 w-3.5" />
          {job?.status === 'processing'
            ? t('progress.recommendations.recommendingStatusProcessing')
            : t('progress.recommendations.recommendingStatusPending')}
        </div>
      ) : null}

      {displayError ? (
        <div
          className="mt-3 flex items-start gap-2 text-sm text-[var(--color-danger)]"
          data-testid="recommend-courses-error"
        >
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{displayError}</span>
        </div>
      ) : null}

      {job?.status === 'completed' && job.result ? (
        <div
          className="animate-fade-in mt-3 rounded-xl bg-[var(--color-primary)]/5 p-4"
          data-testid="recommend-courses-narrative"
        >
          <p className="text-sm leading-relaxed">{job.result.narrative}</p>
          {stats && (stats.mandatoryCount || stats.electiveCount) ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {stats.mandatoryCount ? (
                <Badge tone="primary">
                  {stats.mandatoryCount} {t('progress.recommendations.mandatoryLabel')}
                </Badge>
              ) : null}
              {stats.electiveCount ? (
                <Badge tone="neutral">
                  {stats.electiveCount} {t('progress.recommendations.electiveLabel')}
                </Badge>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </Card>
  )
}
