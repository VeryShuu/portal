import { useQuery } from '@tanstack/vue-query'
import { api } from '../api'
import type { ModuleSettingsResponse } from '../stores/modules'
import { queryKeys } from './keys'

export function useModulesQuery() {
  return useQuery({
    queryKey: queryKeys.modules.settings(),
    queryFn: () => api<ModuleSettingsResponse>('/modules'),
    staleTime: 60_000,
  })
}
