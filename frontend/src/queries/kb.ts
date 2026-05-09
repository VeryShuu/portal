import { computed, toValue, type MaybeRefOrGetter } from 'vue'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import {
  fetchArticles, fetchArticle, fetchTags, fetchSections,
  fetchComments, createComment, deleteComment,
  fetchVersions, restoreVersion,
  type KbArticle,
} from '../api/kb'
import { queryKeys } from './keys'

export function useKbArticlesQuery(params: MaybeRefOrGetter<Parameters<typeof fetchArticles>[0]> = {}) {
  return useQuery({
    queryKey: computed(() => queryKeys.kb.articles(toValue(params) as Record<string, unknown>)),
    queryFn: () => fetchArticles(toValue(params) ?? {}),
    staleTime: 60_000,
  })
}

export function useKbArticleQuery(id: MaybeRefOrGetter<string>) {
  return useQuery({
    queryKey: computed(() => queryKeys.kb.article(toValue(id))),
    queryFn: () => fetchArticle(toValue(id)),
    staleTime: 60_000,
    enabled: computed(() => !!toValue(id)),
  })
}

export function useKbTagsQuery() {
  return useQuery({
    queryKey: queryKeys.kb.tags(),
    queryFn: fetchTags,
    staleTime: 300_000,
  })
}

export function useKbSectionsQuery() {
  return useQuery({
    queryKey: queryKeys.kb.sections(),
    queryFn: fetchSections,
    staleTime: 120_000,
  })
}

export function useKbCommentsQuery(articleId: MaybeRefOrGetter<string>) {
  return useQuery({
    queryKey: computed(() => queryKeys.kb.comments(toValue(articleId))),
    queryFn: () => fetchComments(toValue(articleId), { limit: 50 }),
    staleTime: 30_000,
    enabled: computed(() => !!toValue(articleId)),
  })
}

export function useKbVersionsQuery(articleId: MaybeRefOrGetter<string>) {
  return useQuery({
    queryKey: computed(() => queryKeys.kb.versions(toValue(articleId))),
    queryFn: () => fetchVersions(toValue(articleId), { limit: 50 }),
    staleTime: 60_000,
    enabled: computed(() => !!toValue(articleId)),
  })
}

export function useCreateKbCommentMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ articleId, body }: { articleId: string; body: string }) =>
      createComment(articleId, body),
    onSuccess: (_, { articleId }) => {
      qc.invalidateQueries({ queryKey: queryKeys.kb.comments(articleId) })
    },
  })
}

export function useDeleteKbCommentMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ articleId, commentId }: { articleId: string; commentId: string }) =>
      deleteComment(articleId, commentId),
    onSuccess: (_, { articleId }) => {
      qc.invalidateQueries({ queryKey: queryKeys.kb.comments(articleId) })
    },
  })
}

export function useRestoreKbVersionMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ articleId, versionNum }: { articleId: string; versionNum: number }) =>
      restoreVersion(articleId, versionNum),
    onSuccess: (restored: KbArticle) => {
      qc.setQueryData(queryKeys.kb.article(restored.id), restored)
      qc.invalidateQueries({ queryKey: queryKeys.kb.versions(restored.id) })
    },
  })
}
