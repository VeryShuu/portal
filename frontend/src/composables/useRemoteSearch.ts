import { ref } from 'vue'

export interface RemoteSearchOption {
  label: string
  value: string
}

interface RemoteSearchItem {
  id: string
  full_name: string
  email: string
  status?: string
}

/**
 * Remote-поиск для NSelect (learning, ревью 2026-08-30).
 *
 * Три копии (сотрудники, внешние учётки, методисты) не имели защиты от
 * out-of-order ответов: поздний ответ на старый запрос перезаписывал свежие
 * опции. Здесь устаревшему ответу запрещено трогать состояние (seq-ticket).
 */
export function useRemoteSearch(
  fetch: (q?: string) => Promise<{ items: RemoteSearchItem[] }>,
  opts: { limit?: number; onlyActive?: boolean; onError?: (e: unknown) => void } = {},
) {
  const options = ref<RemoteSearchOption[]>([])
  const searching = ref(false)
  let latest = 0

  async function search(q: string): Promise<void> {
    const ticket = ++latest
    searching.value = true
    try {
      const res = await fetch(q || undefined)
      if (ticket !== latest) return // ответ на устаревший запрос
      options.value = res.items
        .filter((item) => (opts.onlyActive ? item.status === 'active' : true))
        .map((item) => ({ label: `${item.full_name} <${item.email}>`, value: item.id }))
    } catch (e) {
      if (ticket === latest) opts.onError?.(e)
    } finally {
      if (ticket === latest) searching.value = false
    }
  }

  return { options, searching, search }
}
