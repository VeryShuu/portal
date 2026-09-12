/**
 * useHeroStats — агрегирует числа для карточки «Сегодня» на Hero главной.
 *
 * Источники (все существующие — без новых API):
 * - Новости: useNewsListQuery().data.total (всего опубликованных).
 * - Встречи сегодня: useMyMeetingBookingsQuery → фильтр по sameDay(start_time).
 * - Мои задачи: useMyTicketCountsQuery (active helpdesk-тикеты), если модуль
 *   helpdesk включён; иначе 0/скрыто.
 *
 * Все числа вычисляются client-side из уже идущих на главную запросов или
 * недорогих счётчиков. Никаких новых endpoint'ов.
 */
import { computed, type ComputedRef } from 'vue'
import { useNewsListQuery } from '../queries/news'
import { useMyMeetingBookingsQuery } from '../queries/meetings'
import { useMyTicketCountsQuery } from '../queries/helpdesk'
import { useModulesStore } from '../stores/modules'

function isSameDay(iso: string, ref: Date): boolean {
  const d = new Date(iso)
  return (
    d.getFullYear() === ref.getFullYear() &&
    d.getMonth() === ref.getMonth() &&
    d.getDate() === ref.getDate()
  )
}

export interface HeroStats {
  newsCount: number
  meetingsToday: number
  myTasks: number
  /** helpdesk-модуль выключен → «Мои задачи» не показываем */
  showTasks: boolean
  loading: boolean
}

export function useHeroStats(): { stats: ComputedRef<HeroStats> } {
  const modules = useModulesStore()

  const newsQ = useNewsListQuery({ page: 1, page_size: 1 })
  const meetingsEnabled = computed(() => modules.isEnabled('meetings'))
  const helpdeskEnabled = computed(() => modules.isEnabled('helpdesk'))

  // Встречи: тянем ближайшие и фильтруем «сегодня» client-side.
  const meetingsQ = useMyMeetingBookingsQuery(
    { limit: 20 },
    { enabled: meetingsEnabled },
  )
  // Задачи: активные helpdesk-тикеты пользователя (только если модуль включён).
  const ticketsQ = useMyTicketCountsQuery({ enabled: helpdeskEnabled.value })

  const stats = computed<HeroStats>(() => {
    const today = new Date()
    const bookings = meetingsQ.data.value ?? []
    const meetingsToday = bookings.filter((b) => isSameDay(b.start_time, today)).length
    return {
      newsCount: newsQ.data.value?.total ?? 0,
      meetingsToday,
      myTasks: ticketsQ.data.value?.active ?? 0,
      showTasks: helpdeskEnabled.value,
      loading:
        newsQ.isLoading.value ||
        (meetingsEnabled.value && meetingsQ.isLoading.value) ||
        (helpdeskEnabled.value && ticketsQ.isLoading.value),
    }
  })

  return { stats }
}
