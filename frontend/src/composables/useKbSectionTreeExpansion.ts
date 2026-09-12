import { reactive } from 'vue'

const STORAGE_KEY = 'kb.section-tree.expanded'

function loadInitial(): Set<string> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return new Set()
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return new Set()
    return new Set(parsed.filter((x): x is string => typeof x === 'string'))
  } catch {
    return new Set()
  }
}

const expanded = reactive<Set<string>>(loadInitial())

function persist() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(Array.from(expanded)))
  } catch {
    // ignore quota / privacy errors
  }
}

export function useKbSectionTreeExpansion() {
  function isExpanded(id: string): boolean {
    return expanded.has(id)
  }

  function setExpanded(id: string, value: boolean) {
    if (value) {
      if (expanded.has(id)) return
      expanded.add(id)
    } else {
      if (!expanded.has(id)) return
      expanded.delete(id)
    }
    persist()
  }

  function toggle(id: string) {
    setExpanded(id, !expanded.has(id))
  }

  function clear() {
    if (expanded.size === 0) return
    expanded.clear()
    persist()
  }

  return { isExpanded, setExpanded, toggle, clear }
}
