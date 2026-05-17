import { computed, toValue, type MaybeRefOrGetter } from 'vue'
import { keepPreviousData, useQuery } from '@tanstack/vue-query'
import {
  fetchUserById,
  fetchUsers,
  fetchUserDepartments,
  fetchUserOffices,
  adminFetchUserKeycloakGroups,
} from '../api/users'
import { fetchAttributeSchema } from '../api/userAttributeMappings'
import { api } from '../api'
import { queryKeys } from './keys'

export interface StaffSettings {
  phone_extract_regex: string
}

export interface StaffListParams {
  q?: string
  department?: string
  office?: string
  sort?: 'full_name' | 'department' | 'staff_custom'
  page?: number
  page_size?: number
  include_hidden?: boolean
}

export function useStaffListQuery(params: MaybeRefOrGetter<StaffListParams>) {
  return useQuery({
    queryKey: computed(() =>
      queryKeys.users.list(toValue(params) as Record<string, unknown>),
    ),
    queryFn: ({ signal }) => fetchUsers(toValue(params), { signal }),
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  })
}

export function useUserDepartmentsQuery(
  options?: { ordered?: MaybeRefOrGetter<boolean> },
) {
  return useQuery({
    queryKey: computed(() =>
      queryKeys.users.departments(!!toValue(options?.ordered ?? false)),
    ),
    queryFn: () =>
      fetchUserDepartments({ ordered: !!toValue(options?.ordered ?? false) }),
    staleTime: 300_000,
  })
}

export function useUserOfficesQuery() {
  return useQuery({
    queryKey: queryKeys.users.offices(),
    queryFn: fetchUserOffices,
    staleTime: 300_000,
  })
}

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

export function useStaffSettingsQuery() {
  return useQuery({
    queryKey: queryKeys.portal.staffSettings(),
    queryFn: () => api<StaffSettings>('/portal/staff-settings'),
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
