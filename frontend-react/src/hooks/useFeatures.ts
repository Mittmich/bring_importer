import { useQuery } from '@tanstack/react-query'
import { api, type Features } from '@/lib/api'

/**
 * Global feature flags (admin-controlled, see Admin › Features). `features` is
 * undefined until loaded; callers decide what to show meanwhile.
 */
export function useFeatures(): { features: Features | undefined; isLoading: boolean } {
  const { data, isLoading } = useQuery({
    queryKey: ['features'],
    queryFn: api.getFeatures,
    staleTime: 5 * 60_000,
  })
  return { features: data, isLoading }
}
