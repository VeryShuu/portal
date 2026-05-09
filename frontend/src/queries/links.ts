import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import {
  fetchLinks, fetchBookmarks,
  createBookmark, deleteBookmark, reorderBookmarks, reorderLinks,
  type CreateBookmarkDto, type BookmarkReorderItem, type LinkReorderItem,
} from '../api/links'
import { queryKeys } from './keys'

export function useLinksQuery(params?: Parameters<typeof fetchLinks>[0]) {
  return useQuery({
    queryKey: queryKeys.links.list(params as Record<string, unknown>),
    queryFn: () => fetchLinks(params),
    staleTime: 120_000,
  })
}

export function useBookmarksQuery() {
  return useQuery({
    queryKey: queryKeys.links.bookmarks(),
    queryFn: fetchBookmarks,
    staleTime: 120_000,
  })
}

export function useAddBookmarkMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (dto: CreateBookmarkDto) => createBookmark(dto),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.links.bookmarks() })
    },
  })
}

export function useRemoveBookmarkMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deleteBookmark(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.links.bookmarks() })
    },
  })
}

export function useReorderBookmarksMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (items: BookmarkReorderItem[]) => reorderBookmarks(items),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.links.bookmarks() })
    },
  })
}

export function useReorderLinksMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (items: LinkReorderItem[]) => reorderLinks(items),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.links.list() })
    },
  })
}
