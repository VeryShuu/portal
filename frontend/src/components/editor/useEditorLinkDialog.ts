import { computed, reactive, ref, watch } from 'vue'
import type { Ref } from 'vue'
import type { Editor } from '@tiptap/vue-3'
import { useI18n } from 'vue-i18n'

const ALLOWED_LINK_SCHEMES = ['http:', 'https:', 'mailto:', 'tel:'] as const

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

  function openLinkDialog() {
    const ed = editor.value
    if (!ed) return

    linkUrlError.value = ''
    linkUrlAutoToggled = false

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
  }
}
