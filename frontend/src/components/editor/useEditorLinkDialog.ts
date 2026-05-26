import { computed, reactive, ref, watch } from 'vue'
import type { Ref } from 'vue'
import type { Editor } from '@tiptap/vue-3'
import { useI18n } from 'vue-i18n'
import { fetchArticles, type KbArticleListItem } from '@/api/kb'

const ALLOWED_LINK_SCHEMES = ['http:', 'https:', 'mailto:', 'tel:'] as const
const KB_INTERNAL_LINK_RE = /^\/kb\/articles\/([0-9a-f-]{36})(?:[/?#]|$)/i
const KB_SEARCH_DEBOUNCE_MS = 150
const KB_SEARCH_LIMIT = 15
const KB_SEARCH_MIN_LENGTH = 2

export type LinkDialogTab = 'url' | 'kb'

export function useEditorLinkDialog(editor: Ref<Editor | undefined>) {
  const { t } = useI18n()

  const showLinkDialog = ref(false)
  const linkEditingExisting = ref(false)
  const linkHasSelection = ref(false)
  const linkUrlError = ref('')
  const linkForm = reactive({
    url: '',
    text: '',
    newTab: false,
    nofollow: false,
  })

  const linkTab = ref<LinkDialogTab>('url')
  const kbSearchQuery = ref('')
  const kbSearchResults = ref<KbArticleListItem[]>([])
  const kbSearchLoading = ref(false)
  const kbActiveIndex = ref(-1)
  let kbSearchTimer: ReturnType<typeof setTimeout> | null = null
  let kbSearchSeq = 0

  const linkDialogTitle = computed(() =>
    linkEditingExisting.value ? t('editor.link.edit') : t('editor.link.insert'),
  )
  const linkShowTextField = computed(() => !linkHasSelection.value)
  const linkUrlStatus = computed<'error' | undefined>(() => (linkUrlError.value ? 'error' : undefined))
  const canSubmitLink = computed(() => {
    const url = linkForm.url.trim()
    return Boolean(url) && !linkUrlError.value
  })

  let linkUrlAutoToggled = false

  function isExternalUrl(url: string): boolean {
    try {
      const parsed = new URL(url, window.location.origin)
      if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
        return parsed.origin !== window.location.origin
      }
      return parsed.protocol === 'mailto:' || parsed.protocol === 'tel:'
    } catch {
      return false
    }
  }

  function normalizeUrl(raw: string): string {
    const trimmed = raw.trim()
    if (!trimmed) return ''
    if (/^[a-z][a-z0-9+.-]*:/i.test(trimmed) || trimmed.startsWith('/') || trimmed.startsWith('#')) {
      return trimmed
    }
    if (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmed)) {
      return `mailto:${trimmed}`
    }
    return `https://${trimmed}`
  }

  function validateUrl(raw: string): string {
    const trimmed = raw.trim()
    if (!trimmed) return ''
    const candidate = normalizeUrl(trimmed)
    try {
      const parsed = new URL(candidate, window.location.origin)
      if (!ALLOWED_LINK_SCHEMES.includes(parsed.protocol as typeof ALLOWED_LINK_SCHEMES[number])) {
        return t('editor.link.errorScheme')
      }
      return ''
    } catch {
      return t('editor.link.errorInvalid')
    }
  }

  function onLinkUrlChange(value: string) {
    linkUrlError.value = validateUrl(value)
    if (!linkEditingExisting.value && !linkUrlAutoToggled && !linkUrlError.value && value.trim()) {
      const external = isExternalUrl(normalizeUrl(value))
      if (external) {
        linkForm.newTab = true
        linkForm.nofollow = true
        linkUrlAutoToggled = true
      }
    }
  }

  function getSelectedText(): string {
    const ed = editor.value
    if (!ed) return ''
    const { from, to } = ed.state.selection
    if (from === to) return ''
    return ed.state.doc.textBetween(from, to, ' ')
  }

  function isInternalKbLink(url: string): boolean {
    return KB_INTERNAL_LINK_RE.test(url.trim())
  }

  async function runKbSearch(query: string) {
    const trimmed = query.trim()
    kbSearchSeq += 1
    const seq = kbSearchSeq
    if (trimmed.length < KB_SEARCH_MIN_LENGTH) {
      kbSearchResults.value = []
      kbSearchLoading.value = false
      kbActiveIndex.value = -1
      return
    }
    kbSearchLoading.value = true
    try {
      const result = await fetchArticles({
        q: trimmed,
        status: 'published',
        limit: KB_SEARCH_LIMIT,
      })
      if (seq !== kbSearchSeq) return
      kbSearchResults.value = result.items ?? []
      kbActiveIndex.value = kbSearchResults.value.length > 0 ? 0 : -1
    } catch {
      if (seq !== kbSearchSeq) return
      kbSearchResults.value = []
      kbActiveIndex.value = -1
    } finally {
      if (seq === kbSearchSeq) {
        kbSearchLoading.value = false
      }
    }
  }

  function onKbSearchInput(value: string) {
    kbSearchQuery.value = value
    if (kbSearchTimer) clearTimeout(kbSearchTimer)
    kbSearchTimer = setTimeout(() => {
      void runKbSearch(value)
    }, KB_SEARCH_DEBOUNCE_MS)
  }

  function selectKbArticle(item: KbArticleListItem) {
    linkForm.url = `/kb/articles/${item.id}`
    linkUrlError.value = ''
    if (!linkHasSelection.value) {
      linkForm.text = item.title
    }
    linkForm.newTab = false
    linkForm.nofollow = false
    linkUrlAutoToggled = true
    linkTab.value = 'url'
  }

  function onKbKeydown(event: KeyboardEvent) {
    const list = kbSearchResults.value
    if (event.key === 'ArrowDown') {
      if (!list.length) return
      event.preventDefault()
      kbActiveIndex.value = (kbActiveIndex.value + 1) % list.length
    } else if (event.key === 'ArrowUp') {
      if (!list.length) return
      event.preventDefault()
      kbActiveIndex.value =
        kbActiveIndex.value <= 0 ? list.length - 1 : kbActiveIndex.value - 1
    } else if (event.key === 'Enter') {
      if (!list.length) return
      const idx = kbActiveIndex.value >= 0 ? kbActiveIndex.value : 0
      const item = list[idx]
      if (item) {
        event.preventDefault()
        selectKbArticle(item)
      }
    }
  }

  function highlightKbMatch(title: string): Array<{ text: string; match: boolean }> {
    const query = kbSearchQuery.value.trim()
    if (!query) return [{ text: title, match: false }]
    const lowerTitle = title.toLowerCase()
    const lowerQuery = query.toLowerCase()
    const parts: Array<{ text: string; match: boolean }> = []
    let cursor = 0
    let idx = lowerTitle.indexOf(lowerQuery)
    while (idx !== -1) {
      if (idx > cursor) {
        parts.push({ text: title.slice(cursor, idx), match: false })
      }
      parts.push({ text: title.slice(idx, idx + query.length), match: true })
      cursor = idx + query.length
      idx = lowerTitle.indexOf(lowerQuery, cursor)
    }
    if (cursor < title.length) {
      parts.push({ text: title.slice(cursor), match: false })
    }
    return parts
  }

  function openLinkDialog() {
    const ed = editor.value
    if (!ed) return

    linkUrlError.value = ''
    linkUrlAutoToggled = false
    linkTab.value = 'url'
    kbSearchQuery.value = ''
    kbSearchResults.value = []
    kbSearchLoading.value = false
    kbActiveIndex.value = -1

    if (ed.isActive('link')) {
      ed.chain().focus().extendMarkRange('link').run()
      const attrs = ed.getAttributes('link') as { href?: string; target?: string | null; rel?: string | null }
      const href = attrs.href ?? ''
      const rel = attrs.rel ?? ''
      linkEditingExisting.value = true
      linkHasSelection.value = true
      linkForm.url = href
      linkForm.text = getSelectedText()
      linkForm.newTab = attrs.target === '_blank'
      linkForm.nofollow = /\bnofollow\b/.test(rel)
    } else {
      const selected = getSelectedText()
      linkEditingExisting.value = false
      linkHasSelection.value = selected.length > 0
      linkForm.url = ''
      linkForm.text = selected
      linkForm.newTab = false
      linkForm.nofollow = false
    }

    showLinkDialog.value = true
  }

  function buildRel(nofollow: boolean, newTab: boolean): string | null {
    const parts: string[] = []
    if (newTab) parts.push('noopener', 'noreferrer')
    if (nofollow) parts.push('nofollow')
    return parts.length ? Array.from(new Set(parts)).join(' ') : null
  }

  function submitLink() {
    const ed = editor.value
    if (!ed) return
    const error = validateUrl(linkForm.url)
    if (error) {
      linkUrlError.value = error
      return
    }
    const href = normalizeUrl(linkForm.url)
    const rel = buildRel(linkForm.nofollow, linkForm.newTab)
    const target = linkForm.newTab ? '_blank' : null

    const attrs = { href, target, rel }

    if (linkEditingExisting.value) {
      ed.chain().focus().extendMarkRange('link').setLink(attrs).run()
    } else if (linkHasSelection.value) {
      ed.chain().focus().setLink(attrs).run()
    } else {
      const text = linkForm.text.trim() || href
      ed.chain()
        .focus()
        .insertContent({
          type: 'text',
          text,
          marks: [{ type: 'link', attrs }],
        })
        .run()
    }

    showLinkDialog.value = false
  }

  function removeLink() {
    const ed = editor.value
    if (!ed) return
    ed.chain().focus().extendMarkRange('link').unsetLink().run()
    showLinkDialog.value = false
  }

  watch(showLinkDialog, (open) => {
    if (open) return
    linkEditingExisting.value = false
    linkHasSelection.value = false
    linkUrlError.value = ''
    linkForm.url = ''
    linkForm.text = ''
    linkForm.newTab = false
    linkForm.nofollow = false
    linkTab.value = 'url'
    kbSearchQuery.value = ''
    kbSearchResults.value = []
    kbSearchLoading.value = false
    kbActiveIndex.value = -1
    if (kbSearchTimer) {
      clearTimeout(kbSearchTimer)
      kbSearchTimer = null
    }
  })

  return {
    showLinkDialog,
    linkEditingExisting,
    linkForm,
    linkUrlError,
    linkDialogTitle,
    linkShowTextField,
    linkUrlStatus,
    canSubmitLink,
    onLinkUrlChange,
    openLinkDialog,
    submitLink,
    removeLink,
    linkTab,
    kbSearchQuery,
    kbSearchResults,
    kbSearchLoading,
    kbActiveIndex,
    onKbSearchInput,
    onKbKeydown,
    selectKbArticle,
    highlightKbMatch,
    isInternalKbLink,
    kbMinLength: KB_SEARCH_MIN_LENGTH,
  }
}
