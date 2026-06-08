import { computed, toValue, type MaybeRefOrGetter } from 'vue'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import {
  fetchNewsList, fetchNewsById, fetchNewsCategories, fetchNewsUploadLimits,
  fetchGallery, fetchAttachments,
  createNews, updateNews, deleteNews,
  uploadGalleryImage, deleteGalleryImage, reorderGallery,
  uploadAttachment, deleteAttachment,
  fetchNewsPoll, createNewsPoll, updateNewsPoll, deleteNewsPoll,
  closeNewsPoll, reopenNewsPoll, voteNewsPoll, revokeNewsPollVote,
  fetchNewsPollVoters,
  likeNews, unlikeNews,
  fetchNewsComments, createNewsComment, updateNewsComment, deleteNewsComment,
  type CreateNewsDto, type UpdateNewsDto, type ReorderItem,
  type CreateNewsPollRequest, type UpdateNewsPollRequest, type NewsPollVoteRequest,
  type News,
} from '../api/news'
import type { PaginatedResponse } from '../api/index'
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

// ── Polls ─────────────────────────────────────────────────────────────────────

export function useNewsPollQuery(newsId: MaybeRefOrGetter<string>, options?: { enabled?: MaybeRefOrGetter<boolean> }) {
  return useQuery({
    queryKey: computed(() => queryKeys.news.poll(toValue(newsId))),
    queryFn: () => {
      const v = toValue(newsId)
      if (!isValidNewsId(v)) return Promise.resolve(null)
      return fetchNewsPoll(v).catch(() => null)
    },
    staleTime: 10_000,
    enabled: computed(() => isValidNewsId(toValue(newsId)) && (options?.enabled !== undefined ? toValue(options.enabled) : true)),
  })
}

export function useNewsPollVotersQuery(
  newsId: MaybeRefOrGetter<string>,
  options?: { enabled?: MaybeRefOrGetter<boolean> },
) {
  return useQuery({
    queryKey: computed(() => queryKeys.news.pollVoters(toValue(newsId))),
    queryFn: () => {
      const v = toValue(newsId)
      if (!isValidNewsId(v)) return Promise.resolve([])
      return fetchNewsPollVoters(v)
    },
    staleTime: 10_000,
    enabled: computed(
      () =>
        isValidNewsId(toValue(newsId)) &&
        (options?.enabled !== undefined ? toValue(options.enabled) : true),
    ),
  })
}

export function useCreateNewsPollMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ newsId, dto }: { newsId: string; dto: CreateNewsPollRequest }) => createNewsPoll(newsId, dto),
    onSuccess: (_, { newsId }) => {
      qc.invalidateQueries({ queryKey: queryKeys.news.poll(newsId) })
      qc.invalidateQueries({ queryKey: queryKeys.news.detail(newsId) })
    },
  })
}

export function useUpdateNewsPollMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ newsId, dto }: { newsId: string; dto: UpdateNewsPollRequest }) => updateNewsPoll(newsId, dto),
    onSuccess: (_, { newsId }) => {
      qc.invalidateQueries({ queryKey: queryKeys.news.poll(newsId) })
    },
  })
}

export function useDeleteNewsPollMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (newsId: string) => deleteNewsPoll(newsId),
    onSuccess: (_, newsId) => {
      qc.removeQueries({ queryKey: queryKeys.news.poll(newsId) })
      qc.invalidateQueries({ queryKey: queryKeys.news.detail(newsId) })
    },
  })
}

export function useCloseNewsPollMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (newsId: string) => closeNewsPoll(newsId),
    onSuccess: (_, newsId) => {
      qc.invalidateQueries({ queryKey: queryKeys.news.poll(newsId) })
    },
  })
}

export function useReopenNewsPollMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (newsId: string) => reopenNewsPoll(newsId),
    onSuccess: (_, newsId) => {
      qc.invalidateQueries({ queryKey: queryKeys.news.poll(newsId) })
    },
  })
}

export function useVoteNewsPollMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ newsId, dto }: { newsId: string; dto: NewsPollVoteRequest }) => voteNewsPoll(newsId, dto),
    onSuccess: (_, { newsId }) => {
      qc.invalidateQueries({ queryKey: queryKeys.news.poll(newsId) })
      qc.invalidateQueries({ queryKey: queryKeys.news.pollVoters(newsId) })
    },
  })
}

export function useRevokeNewsPollVoteMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (newsId: string) => revokeNewsPollVote(newsId),
    onSuccess: (_, newsId) => {
      qc.invalidateQueries({ queryKey: queryKeys.news.poll(newsId) })
      qc.invalidateQueries({ queryKey: queryKeys.news.pollVoters(newsId) })
    },
  })
}

// ── Likes ─────────────────────────────────────────────────────────────────────

function applyLikeToCaches(qc: ReturnType<typeof useQueryClient>, id: string, liked: boolean) {
  const patch = (n: News): News =>
    n.id === id
      ? {
          ...n,
          liked_by_me: liked,
          like_count: Math.max(0, n.like_count + (liked ? 1 : -1)),
        }
      : n

  const detail = qc.getQueryData<News>(queryKeys.news.detail(id))
  if (detail) qc.setQueryData(queryKeys.news.detail(id), patch(detail))

  qc.setQueriesData<PaginatedResponse<News>>(
    { queryKey: queryKeys.news.all },
    (old) => (old?.items ? { ...old, items: old.items.map(patch) } : old),
  )
}

export function useToggleNewsLikeMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, liked }: { id: string; liked: boolean }) =>
      liked ? likeNews(id) : unlikeNews(id),
    onMutate: async ({ id, liked }) => {
      await qc.cancelQueries({ queryKey: queryKeys.news.detail(id) })
      await qc.cancelQueries({ queryKey: queryKeys.news.all })
      const prevDetail = qc.getQueryData<News>(queryKeys.news.detail(id))
      const prevLists = qc.getQueriesData<PaginatedResponse<News>>({ queryKey: queryKeys.news.all })
      applyLikeToCaches(qc, id, liked)
      return { prevDetail, prevLists }
    },
    onError: (_e, { id }, ctx) => {
      if (ctx?.prevDetail) qc.setQueryData(queryKeys.news.detail(id), ctx.prevDetail)
      ctx?.prevLists?.forEach(([key, data]) => qc.setQueryData(key, data))
    },
    onSettled: (_d, _e, { id }) => {
      qc.invalidateQueries({ queryKey: queryKeys.news.detail(id) })
      qc.invalidateQueries({ queryKey: queryKeys.news.list() })
    },
  })
}

// ── Comments ──────────────────────────────────────────────────────────────────

export function useNewsCommentsQuery(
  newsId: MaybeRefOrGetter<string>,
  options?: { enabled?: MaybeRefOrGetter<boolean> },
) {
  return useQuery({
    queryKey: computed(() => queryKeys.news.comments(toValue(newsId))),
    queryFn: () => {
      const v = toValue(newsId)
      if (!isValidNewsId(v)) return Promise.resolve({ items: [], total: 0 })
      return fetchNewsComments(v)
    },
    staleTime: 10_000,
    enabled: computed(
      () =>
        isValidNewsId(toValue(newsId)) &&
        (options?.enabled !== undefined ? toValue(options.enabled) : true),
    ),
  })
}

export function useCreateNewsCommentMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ newsId, body }: { newsId: string; body: string }) =>
      createNewsComment(newsId, body),
    onSuccess: (_, { newsId }) => {
      qc.invalidateQueries({ queryKey: queryKeys.news.comments(newsId) })
      qc.invalidateQueries({ queryKey: queryKeys.news.detail(newsId) })
      qc.invalidateQueries({ queryKey: queryKeys.news.list() })
    },
  })
}

export function useUpdateNewsCommentMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ newsId, commentId, body }: { newsId: string; commentId: string; body: string }) =>
      updateNewsComment(newsId, commentId, body),
    onSuccess: (_, { newsId }) => {
      qc.invalidateQueries({ queryKey: queryKeys.news.comments(newsId) })
    },
  })
}

export function useDeleteNewsCommentMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ newsId, commentId }: { newsId: string; commentId: string }) =>
      deleteNewsComment(newsId, commentId),
    onSuccess: (_, { newsId }) => {
      qc.invalidateQueries({ queryKey: queryKeys.news.comments(newsId) })
      qc.invalidateQueries({ queryKey: queryKeys.news.detail(newsId) })
      qc.invalidateQueries({ queryKey: queryKeys.news.list() })
    },
  })
}
