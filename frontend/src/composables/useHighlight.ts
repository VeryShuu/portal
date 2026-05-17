import { toValue, type MaybeRefOrGetter } from 'vue'

const ESCAPE_HTML: Record<string, string> = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;',
}

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ESCAPE_HTML[c])
}

function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

export function useHighlight(query: MaybeRefOrGetter<string | undefined | null>) {
  return (text: string | null | undefined): string => {
    const safe = escapeHtml(text ?? '')
    const q = (toValue(query) ?? '').trim()
    if (!q) return safe
    const re = new RegExp(`(${escapeRegex(escapeHtml(q))})`, 'gi')
    return safe.replace(re, '<mark class="staff-hl">$1</mark>')
  }
}
