import { computed, toValue, type MaybeRefOrGetter } from 'vue'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import {
  fetchDirectories,
  createDirectory,
  updateDirectory,
  deleteDirectory,
  fetchEntries,
  fetchEntry,
  createEntry,
  updateEntry,
  deleteEntry,
  reorderEntries,
  type CreateDirectoryDto,
  type UpdateDirectoryDto,
  type CreateEntryDto,
  type UpdateEntryDto,
  type EntryReorderItem,
} from '../api/directories'
import { queryKeys } from './keys'

export function useDirectoriesQuery(options: { enabled?: MaybeRefOrGetter<boolean> } = {}) {
  return useQuery({
    queryKey: queryKeys.directories.list(),
    queryFn: () => fetchDirectories(),
    staleTime: 60_000,
    enabled: computed(() => (options.enabled === undefined ? true : !!toValue(options.enabled))),
  })
}

export function useDirectoryEntriesQuery(
  slug: MaybeRefOrGetter<string>,
  params: MaybeRefOrGetter<{ q?: string; limit?: number; offset?: number }> = {},
  options: { enabled?: MaybeRefOrGetter<boolean> } = {},
) {
  return useQuery({
    queryKey: computed(() =>
      queryKeys.directories.entries(toValue(slug), toValue(params) as Record<string, unknown>),
    ),
    queryFn: () => fetchEntries(toValue(slug), toValue(params)),
    staleTime: 30_000,
    placeholderData: (prev) => prev,
    enabled: computed(
      () => !!toValue(slug) && (options.enabled === undefined ? true : !!toValue(options.enabled)),
    ),
  })
}

export function useDirectoryEntryQuery(
  slug: MaybeRefOrGetter<string>,
  entryId: MaybeRefOrGetter<string>,
) {
  return useQuery({
    queryKey: computed(() => queryKeys.directories.entry(toValue(slug), toValue(entryId))),
    queryFn: () => fetchEntry(toValue(slug), toValue(entryId)),
    staleTime: 30_000,
    enabled: computed(() => !!toValue(slug) && !!toValue(entryId)),
  })
}

export function useCreateDirectoryMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (dto: CreateDirectoryDto) => createDirectory(dto),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.directories.list() })
    },
  })
}

export function useUpdateDirectoryMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, dto }: { id: string; dto: UpdateDirectoryDto }) => updateDirectory(id, dto),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.directories.all })
    },
  })
}

export function useDeleteDirectoryMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deleteDirectory(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.directories.all })
    },
  })
}

export function useCreateEntryMutation(slug: MaybeRefOrGetter<string>) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (dto: CreateEntryDto) => createEntry(toValue(slug), dto),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.directories.entries(toValue(slug)) })
    },
  })
}

export function useUpdateEntryMutation(slug: MaybeRefOrGetter<string>) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, dto }: { id: string; dto: UpdateEntryDto }) =>
      updateEntry(toValue(slug), id, dto),
    onSuccess: (_, { id }) => {
      qc.invalidateQueries({ queryKey: queryKeys.directories.entries(toValue(slug)) })
      qc.invalidateQueries({ queryKey: queryKeys.directories.entry(toValue(slug), id) })
    },
  })
}

export function useDeleteEntryMutation(slug: MaybeRefOrGetter<string>) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deleteEntry(toValue(slug), id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.directories.entries(toValue(slug)) })
    },
  })
}

export function useReorderEntriesMutation(slug: MaybeRefOrGetter<string>) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (items: EntryReorderItem[]) => reorderEntries(toValue(slug), items),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.directories.entries(toValue(slug)) })
    },
  })
}
