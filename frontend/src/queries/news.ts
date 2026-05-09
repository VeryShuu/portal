import { computed, toValue, type MaybeRefOrGetter } from 'vue'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import {
  fetchNewsList, fetchNewsById, fetchNewsCategories, fetchNewsUploadLimits,
  fetchGallery, fetchAttachments,
  createNews, updateNews, deleteNews,
  type CreateNewsDto, type UpdateNewsDto,
} from '../api/news'
import { queryKeys } from './keys'

export function useNewsListQuery(params: MaybeRefOrGetter<Parameters<typeof fetchNewsList>[0]> = {}) {
  return useQuery({
    queryKey: computed(() => queryKeys.news.list(toValue(params) as Record<string, unknown>)),
    queryFn: () => fetchNewsList(toValue(params) ?? {}),
    staleTime: 0,
  })
}

export function useNewsDetailQuery(id: MaybeRefOrGetter<string>) {
  return useQuery({
    queryKey: computed(() => queryKeys.news.detail(toValue(id))),
    queryFn: () => fetchNewsById(toValue(id)),
    staleTime: 60_000,
    enabled: computed(() => !!toValue(id)),
  })
}

export function useNewsGalleryQuery(newsId: MaybeRefOrGetter<string>, options?: { enabled?: MaybeRefOrGetter<boolean> }) {
  return useQuery({
    queryKey: computed(() => queryKeys.news.gallery(toValue(newsId))),
    queryFn: () => fetchGallery(toValue(newsId)).catch(() => []),
    staleTime: 60_000,
    placeholderData: [],
    enabled: computed(() => !!toValue(newsId) && (options?.enabled !== undefined ? toValue(options.enabled) : true)),
  })
}

export function useNewsAttachmentsQuery(newsId: MaybeRefOrGetter<string>, options?: { enabled?: MaybeRefOrGetter<boolean> }) {
  return useQuery({
    queryKey: computed(() => queryKeys.news.attachments(toValue(newsId))),
    queryFn: () => fetchAttachments(toValue(newsId)).catch(() => []),
    staleTime: 60_000,
    placeholderData: [],
    enabled: computed(() => !!toValue(newsId) && (options?.enabled !== undefined ? toValue(options.enabled) : true)),
  })
}

export function useNewsCategoriesQuery() {
  return useQuery({
    queryKey: queryKeys.news.categories(),
    queryFn: fetchNewsCategories,
    staleTime: 300_000,
  })
}

export function useNewsUploadLimitsQuery() {
  return useQuery({
    queryKey: queryKeys.news.limits(),
    queryFn: fetchNewsUploadLimits,
    staleTime: 300_000,
  })
}

export function useCreateNewsMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (dto: CreateNewsDto) => createNews(dto),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.news.all })
    },
  })
}

export function useUpdateNewsMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, dto }: { id: string; dto: UpdateNewsDto }) => updateNews(id, dto),
    onSuccess: (_, { id }) => {
      qc.invalidateQueries({ queryKey: queryKeys.news.all })
      qc.invalidateQueries({ queryKey: queryKeys.news.detail(id) })
    },
  })
}

export function useDeleteNewsMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deleteNews(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.news.all })
    },
  })
}
