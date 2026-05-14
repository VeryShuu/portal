import { computed, toValue, type MaybeRefOrGetter } from 'vue'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import {
  fetchNewsList, fetchNewsById, fetchNewsCategories, fetchNewsUploadLimits,
  fetchGallery, fetchAttachments,
  createNews, updateNews, deleteNews,
  uploadGalleryImage, deleteGalleryImage, reorderGallery,
  uploadAttachment, deleteAttachment,
  type CreateNewsDto, type UpdateNewsDto, type ReorderItem,
} from '../api/news'
import { queryKeys } from './keys'

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
function isValidNewsId(v: unknown): v is string {
  return typeof v === 'string' && UUID_RE.test(v)
}

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
    queryFn: () => {
      const v = toValue(id)
      if (!isValidNewsId(v)) throw new Error('invalid news id')
      return fetchNewsById(v)
    },
    staleTime: 60_000,
    enabled: computed(() => isValidNewsId(toValue(id))),
  })
}

export function useNewsGalleryQuery(newsId: MaybeRefOrGetter<string>, options?: { enabled?: MaybeRefOrGetter<boolean> }) {
  return useQuery({
    queryKey: computed(() => queryKeys.news.gallery(toValue(newsId))),
    queryFn: () => {
      const v = toValue(newsId)
      if (!isValidNewsId(v)) return Promise.resolve([])
      return fetchGallery(v).catch(() => [])
    },
    staleTime: 60_000,
    placeholderData: [],
    enabled: computed(() => isValidNewsId(toValue(newsId)) && (options?.enabled !== undefined ? toValue(options.enabled) : true)),
  })
}

export function useNewsAttachmentsQuery(newsId: MaybeRefOrGetter<string>, options?: { enabled?: MaybeRefOrGetter<boolean> }) {
  return useQuery({
    queryKey: computed(() => queryKeys.news.attachments(toValue(newsId))),
    queryFn: () => {
      const v = toValue(newsId)
      if (!isValidNewsId(v)) return Promise.resolve([])
      return fetchAttachments(v).catch(() => [])
    },
    staleTime: 60_000,
    placeholderData: [],
    enabled: computed(() => isValidNewsId(toValue(newsId)) && (options?.enabled !== undefined ? toValue(options.enabled) : true)),
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
    onSuccess: (_, id) => {
      qc.removeQueries({ queryKey: queryKeys.news.detail(id) })
      qc.removeQueries({ queryKey: queryKeys.news.gallery(id) })
      qc.removeQueries({ queryKey: queryKeys.news.attachments(id) })
      qc.invalidateQueries({ queryKey: queryKeys.news.all })
    },
  })
}

export function useUploadGalleryImageMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ newsId, file }: { newsId: string; file: File }) =>
      uploadGalleryImage(newsId, file),
    onSuccess: (_, { newsId }) => {
      qc.invalidateQueries({ queryKey: queryKeys.news.gallery(newsId) })
    },
  })
}

export function useDeleteGalleryImageMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ newsId, imgId }: { newsId: string; imgId: string }) =>
      deleteGalleryImage(newsId, imgId),
    onSuccess: (_, { newsId }) => {
      qc.invalidateQueries({ queryKey: queryKeys.news.gallery(newsId) })
    },
  })
}

export function useReorderGalleryMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ newsId, items }: { newsId: string; items: ReorderItem[] }) =>
      reorderGallery(newsId, items),
    onSuccess: (_, { newsId }) => {
      qc.invalidateQueries({ queryKey: queryKeys.news.gallery(newsId) })
    },
  })
}

export function useUploadAttachmentMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ newsId, file }: { newsId: string; file: File }) =>
      uploadAttachment(newsId, file),
    onSuccess: (_, { newsId }) => {
      qc.invalidateQueries({ queryKey: queryKeys.news.attachments(newsId) })
    },
  })
}

export function useDeleteAttachmentMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ newsId, attId }: { newsId: string; attId: string }) =>
      deleteAttachment(newsId, attId),
    onSuccess: (_, { newsId }) => {
      qc.invalidateQueries({ queryKey: queryKeys.news.attachments(newsId) })
    },
  })
}
