import { computed, toValue, type MaybeRefOrGetter } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { fetchUserById, adminFetchUserKeycloakGroups } from '../api/users'
import { fetchAttributeSchema } from '../api/userAttributeMappings'
import { queryKeys } from './keys'

export function useUserQuery(
  id: MaybeRefOrGetter<string>,
  options?: { enabled?: MaybeRefOrGetter<boolean> },
) {
  return useQuery({
    queryKey: computed(() => queryKeys.users.detail(toValue(id))),
    queryFn: () => fetchUserById(toValue(id)),
    staleTime: 60_000,
    enabled: computed(() =>
      !!toValue(id) &&
      (options?.enabled !== undefined ? !!toValue(options.enabled) : true),
    ),
  })
}

export function useUserAttributeSchemaQuery() {
  return useQuery({
    queryKey: queryKeys.users.attributeSchema(),
    queryFn: fetchAttributeSchema,
    staleTime: 300_000,
  })
}

export function useUserKeycloakGroupsQuery(
  id: MaybeRefOrGetter<string>,
  options?: { enabled?: MaybeRefOrGetter<boolean> },
) {
  return useQuery({
    queryKey: computed(() => queryKeys.users.keycloakGroups(toValue(id))),
    queryFn: () => adminFetchUserKeycloakGroups(toValue(id)),
    staleTime: 120_000,
    enabled: computed(() =>
      !!toValue(id) &&
      (options?.enabled !== undefined ? !!toValue(options.enabled) : true),
    ),
  })
}
