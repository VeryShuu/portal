import { ref } from 'vue'

const RECENT_KEY = 'gs-recent'
const RECENT_MAX = 8

export function useSearchRecent() {
  const recent = ref<string[]>(loadRecent())

  function loadRecent(): string[] {
    try {
      const raw = localStorage.getItem(RECENT_KEY)
      if (!raw) return []
      const parsed = JSON.parse(raw)
      if (!Array.isArray(parsed)) return []
      return parsed.filter((item): item is string => typeof item === 'string')
    } catch {
      return []
    }
  }

  function saveRecent(q: string) {
    if (!q.trim()) return
    const list = [q, ...recent.value.filter((x) => x !== q)].slice(0, RECENT_MAX)
    recent.value = list
    localStorage.setItem(RECENT_KEY, JSON.stringify(list))
  }

  return { recent, saveRecent }
}
