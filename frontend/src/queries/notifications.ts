import { computed, toValue, type MaybeRefOrGetter } from 'vue'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import {
  fetchNotifications, fetchUnreadCount,
  markRead, markAllRead, deleteNotification,
} from '../api/notifications'
import { queryKeys } from './keys'

export function useNotificationsQuery(params?: MaybeRefOrGetter<{ unread_only?: boolean; limit?: number }>) {
  return useQuery({
    queryKey: computed(() => queryKeys.notifications.list(toValue(params) as Record<string, unknown> ?? {})),
    queryFn: () => fetchNotifications(toValue(params) ?? {}),
    staleTime: 30_000,
  })
}

export function useUnreadCountQuery() {
  return useQuery({
    queryKey: queryKeys.notifications.unreadCount(),
    queryFn: fetchUnreadCount,
    staleTime: 30_000,
    refetchInterval: 60_000,
  })
}

export function useMarkReadMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => markRead(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.notifications.all })
    },
  })
}

export function useMarkAllReadMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => markAllRead(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.notifications.all })
    },
  })
}

export function useDeleteNotificationMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deleteNotification(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.notifications.all })
    },
  })
}
