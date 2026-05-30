import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { saveDraft, type KbSection } from '../../api/kb'

interface LocalDraftPayload {
  title: string
  body: string
  section_id: string | null
  status: 'draft' | 'published'
  tags: string[]
  savedAt: number
}

interface KbSectionOption {
  label: string
  key: string
  children?: KbSectionOption[]
  [k: string]: unknown
}

const DRAFT_DEBOUNCE_MS = 7_000

function sectionToOption(s: KbSection): KbSectionOption {
  return {
    label: s.title,
    key: s.id,
    children: s.children.length ? s.children.map(sectionToOption) : undefined,
  }
}

function getErrorStatus(err: unknown): number | undefined {
  const e = err as {
    status?: number
    statusCode?: number
    response?: { status?: number }
  } | null
  return e?.response?.status ?? e?.status ?? e?.statusCode
}

export function isBodyEmpty(html: string): boolean {
  const stripped = html.replace(/<[^>]*>/g, '').replace(/&nbsp;/g, ' ').trim()
  return stripped.length === 0
}

export function useArticleFormState(options: {
  isEdit: ComputedRef<boolean>
  articleId: ComputedRef<string | undefined>
  localDraftKey: ComputedRef<string>
  t: (key: string, values?: Record<string, unknown>) => string
  locale: Ref<string>
  message: { error: (s: string) => void }
}) {
  const { isEdit, articleId, localDraftKey, t, locale, message } = options

  const form = ref({
    title: '',
    body: '',
    section_id: null as string | null,
    status: 'draft' as 'draft' | 'published',
    tags: [] as string[],
    change_comment: '',
  })

  const currentVersion = ref(1)
  const saving = ref(false)
  const savingDraft = ref(false)
  const draftConflict = ref(false)
  const draftSavedAt = ref<Date | null>(null)
  const sections = ref<KbSection[]>([])
  const lastSavedTitle = ref('')
  const lastSavedBody = ref('')
  const showRecoveryBanner = ref(false)
  const pendingLocalDraft = ref<LocalDraftPayload | null>(null)
  const draftRelativeLabel = ref('')
  let suppressNextWatch = false
  let draftDebounceTimer: ReturnType<typeof setTimeout> | null = null
  let relativeTicker: ReturnType<typeof setInterval> | null = null

  const statusOptions = computed(() => [
    { label: t('kb.status.draft'), value: 'draft' },
    { label: t('kb.status.published'), value: 'published' },
  ])

  const sectionOptions = computed(() => sections.value.map(sectionToOption))

  function formatTime(d: Date) {
    return d.toLocaleTimeString(locale.value === 'ru' ? 'ru-RU' : 'en-US', {
      hour: '2-digit', minute: '2-digit',
    })
  }

  function formatRelative(d: Date): string {
    const diffSec = Math.max(0, Math.floor((Date.now() - d.getTime()) / 1000))
    if (diffSec < 5) return t('kb.draft.justNow')
    if (diffSec < 60) return t('kb.draft.secondsAgo', { n: diffSec })
    const diffMin = Math.floor(diffSec / 60)
    if (diffMin < 60) return t('kb.draft.minutesAgo', { n: diffMin })
    return formatTime(d)
  }

  const draftIndicator = computed(() => {
    if (savingDraft.value) return t('kb.draft.saving')
    if (!draftSavedAt.value) return ''
    return `✓ ${t('kb.draftSaved')} ${draftRelativeLabel.value}`
  })

  const recoveryTimeLabel = computed(() => {
    if (!pendingLocalDraft.value) return ''
    return formatTime(new Date(pendingLocalDraft.value.savedAt))
  })

  function writeLocalDraft() {
    if (typeof window === 'undefined') return
    if (!form.value.title.trim() && !form.value.body.trim()) {
      clearLocalDraft()
      return
    }
    const payload: LocalDraftPayload = {
      title: form.value.title,
      body: form.value.body,
      section_id: form.value.section_id,
      status: form.value.status,
      tags: [...form.value.tags],
      savedAt: Date.now(),
    }
    try {
      window.localStorage.setItem(localDraftKey.value, JSON.stringify(payload))
      draftSavedAt.value = new Date(payload.savedAt)
      draftRelativeLabel.value = formatRelative(draftSavedAt.value)
    } catch {
      /* ignore quota errors */
    }
  }

  function clearLocalDraft() {
    if (typeof window === 'undefined') return
    try {
      window.localStorage.removeItem(localDraftKey.value)
    } catch {
      /* ignore */
    }
  }

  function readLocalDraft(): LocalDraftPayload | null {
    if (typeof window === 'undefined') return null
    try {
      const raw = window.localStorage.getItem(localDraftKey.value)
      if (!raw) return null
      const parsed = JSON.parse(raw) as LocalDraftPayload
      if (!parsed || typeof parsed !== 'object') return null
      return parsed
    } catch {
      return null
    }
  }

  function cancelDraftDebounce() {
    if (draftDebounceTimer) {
      clearTimeout(draftDebounceTimer)
      draftDebounceTimer = null
    }
  }

  function scheduleDraftSave() {
    cancelDraftDebounce()
    draftDebounceTimer = setTimeout(() => {
      if (isEdit.value && articleId.value && form.value.status === 'draft') {
        void onSaveDraft({ silent: true })
      } else {
        writeLocalDraft()
      }
    }, DRAFT_DEBOUNCE_MS)
  }

  async function onSaveDraft(opts: { silent?: boolean } = {}) {
    if (!articleId.value) return
    if (savingDraft.value) return
    if (
      form.value.title === lastSavedTitle.value &&
      form.value.body === lastSavedBody.value
    ) {
      return
    }
    savingDraft.value = true
    try {
      const saved = await saveDraft(articleId.value, {
        title: form.value.title,
        body: form.value.body,
        version: currentVersion.value,
      })
      if (saved?.version) currentVersion.value = saved.version
      lastSavedTitle.value = form.value.title
      lastSavedBody.value = form.value.body
      draftSavedAt.value = new Date()
      draftRelativeLabel.value = formatRelative(draftSavedAt.value)
      clearLocalDraft()
    } catch (err: unknown) {
      const status = getErrorStatus(err)
      if (status === 409) {
        cancelDraftDebounce()
        draftConflict.value = true
        if (!opts.silent) message.error(t('kb.conflictError'))
      } else if (!opts.silent) {
        message.error(t('common.errorOccurred'))
      }
    } finally {
      savingDraft.value = false
    }
  }

  function applyLocalDraft() {
    const draft = pendingLocalDraft.value
    if (!draft) return
    suppressNextWatch = true
    form.value.title = draft.title
    form.value.body = draft.body
    form.value.section_id = draft.section_id
    form.value.status = draft.status
    form.value.tags = [...draft.tags]
    draftSavedAt.value = new Date(draft.savedAt)
    draftRelativeLabel.value = formatRelative(draftSavedAt.value)
    showRecoveryBanner.value = false
    pendingLocalDraft.value = null
  }

  function dismissLocalDraft() {
    clearLocalDraft()
    showRecoveryBanner.value = false
    pendingLocalDraft.value = null
  }

  function handleBeforeUnload() {
    if (draftDebounceTimer) {
      writeLocalDraft()
    }
  }

  function startRelativeTicker() {
    relativeTicker = setInterval(() => {
      if (draftSavedAt.value) {
        draftRelativeLabel.value = formatRelative(draftSavedAt.value)
      }
    }, 5_000)
  }

  function stopRelativeTicker() {
    if (relativeTicker) {
      clearInterval(relativeTicker)
      relativeTicker = null
    }
  }

  function initFromArticle(art: {
    title: string
    body: string
    section_id: string | null
    status: string
    tags: Array<{ name: string }>
    version: number
  }) {
    suppressNextWatch = true
    form.value.title = art.title
    form.value.body = art.body
    form.value.section_id = art.section_id
    form.value.status = art.status === 'archived' ? 'draft' : (art.status as 'draft' | 'published')
    form.value.tags = art.tags.map((tag) => tag.name)
    currentVersion.value = art.version
    lastSavedTitle.value = art.title
    lastSavedBody.value = art.body
  }

  watch(
    () => [form.value.title, form.value.body, form.value.section_id, form.value.status, form.value.tags] as const,
    () => {
      if (suppressNextWatch) {
        suppressNextWatch = false
        return
      }
      scheduleDraftSave()
    },
    { deep: true },
  )

  return {
    form,
    currentVersion,
    saving,
    savingDraft,
    draftConflict,
    draftSavedAt,
    sections,
    lastSavedTitle,
    lastSavedBody,
    showRecoveryBanner,
    pendingLocalDraft,
    draftRelativeLabel,
    statusOptions,
    sectionOptions,
    draftIndicator,
    recoveryTimeLabel,
    onSaveDraft,
    cancelDraftDebounce,
    writeLocalDraft,
    clearLocalDraft,
    readLocalDraft,
    scheduleDraftSave,
    applyLocalDraft,
    dismissLocalDraft,
    handleBeforeUnload,
    startRelativeTicker,
    stopRelativeTicker,
    initFromArticle,
  }
}
