import { useQuery } from '@tanstack/react-query'
import { aiJobsApi } from '../api/endpoints'

export function useAiJobPolling(jobId: string | null, { intervalMs = 2000 }: { intervalMs?: number } = {}) {
  return useQuery({
    queryKey: ['aiJobs', jobId],
    queryFn: () => aiJobsApi.get(jobId as string),
    enabled: !!jobId,
    retry: false,
    refetchInterval: (query) => {
      if (query.state.error) return false
      const status = query.state.data?.aiJob.status
      return status === 'completed' || status === 'failed' ? false : intervalMs
    },
  })
}
