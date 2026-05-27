<template>
  <div class="form-wrap">
    <div class="form-header">
      <h1 class="u-page-head__title">
        {{ isEdit ? t('kb.editArticle') : t('kb.createArticle') }}
      </h1>
      <div
        v-if="draftIndicator"
        class="draft-saved"
        :class="{ 'is-saving': savingDraft }"
      >
        {{ draftIndicator }}
      </div>
    </div>

    <n-alert
      v-if="draftConflict"
      class="recovery-banner"
      type="warning"
      :show-icon="true"
      :closable="false"
    >
      <template #header>
        {{ t('kb.draft.conflictTitle') }}
      </template>
      <div class="recovery-actions">
        <span>{{ t('kb.draft.conflictHint') }}</span>
        <n-button
          size="small"
          type="primary"
          @click="reloadPage"
        >
          {{ t('kb.draft.reload') }}
        </n-button>
      </div>
    </n-alert>

    <n-alert
      v-if="showRecoveryBanner"
      class="recovery-banner"
      type="info"
      :show-icon="true"
      :closable="false"
    >
      <template #header>
        {{ t('kb.draft.recoverTitle', { time: recoveryTimeLabel }) }}
      </template>
      <div class="recovery-actions">
        <n-button
          size="small"
          type="primary"
          @click="applyLocalDraft"
        >
          {{ t('kb.draft.recover') }}
        </n-button>
        <n-button
          size="small"
          @click="dismissLocalDraft"
        >
          {{ t('kb.draft.discard') }}
        </n-button>
      </div>
    </n-alert>

    <n-form
      :model="form"
      label-placement="top"
    >
      <n-grid
        :cols="2"
        :x-gap="16"
      >
        <n-gi :span="2">
          <n-form-item
            :label="t('kb.form.title')"
            required
          >
            <n-input
              v-model:value="form.title"
              :placeholder="t('kb.form.titlePlaceholder')"
              size="large"
              style="font-size:20px;font-weight:700"
            />
          </n-form-item>
        </n-gi>

        <n-gi>
          <n-form-item :label="t('kb.form.section')">
            <n-tree-select
              v-model:value="form.section_id"
              :options="sectionOptions"
              :placeholder="t('kb.form.sectionPlaceholder')"
              clearable
              style="width:100%"
            />
          </n-form-item>
        </n-gi>

        <n-gi>
          <n-form-item :label="t('kb.form.status')">
            <n-select
              v-model:value="form.status"
              :options="statusOptions"
              style="width:100%"
            />
          </n-form-item>
        </n-gi>

        <n-gi :span="2">
          <n-form-item :label="t('kb.form.tags')">
            <n-dynamic-tags v-model:value="form.tags" />
          </n-form-item>
        </n-gi>

        <n-gi :span="2">
          <n-form-item
            :label="t('kb.form.body')"
            required
          >
            <RichEditor
              v-model="form.body"
              :placeholder="t('kb.form.bodyPlaceholder')"
              :upload-endpoint="articleId ? `/api/v1/kb/articles/${articleId}/media` : undefined"
              style="width:100%"
            />
          </n-form-item>
        </n-gi>

        <n-gi v-if="isEdit">
          <n-form-item :label="t('kb.form.changeComment')">
            <n-input
              v-model:value="form.change_comment"
              :placeholder="t('kb.form.changeCommentPlaceholder')"
            />
          </n-form-item>
        </n-gi>

        <n-gi
          v-if="isEdit && articleId"
          :span="2"
        >
          <n-form-item :label="t('kb.files.title')">
            <KbAttachmentsPanel
              :article-id="articleId"
              :can-upload="true"
              style="width:100%"
            />
          </n-form-item>
        </n-gi>
      </n-grid>

      <div class="form-actions u-flex u-justify-end u-gap-12">
        <n-button @click="router.back()">
          {{ t('common.cancel') }}
        </n-button>
        <n-button
          v-if="isEdit"
          :loading="savingDraft"
          @click="() => onSaveDraft()"
        >
          {{ t('kb.saveDraft') }}
        </n-button>
        <n-button
          type="primary"
          :loading="saving"
          @click="onSubmit"
        >
          {{ isEdit ? t('common.save') : t('kb.publish') }}
        </n-button>
      </div>
    </n-form>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import {
  NForm, NFormItem, NInput, NSelect, NButton, NGrid, NGi,
  NDynamicTags, NTreeSelect, NAlert,
} from 'naive-ui'
import RichEditor from '../components/RichEditor.vue'
import KbAttachmentsPanel from '../components/KbAttachmentsPanel.vue'
import { fetchSections, fetchArticle, saveDraft, type KbSection } from '../api/kb'
import { useCreateKbArticleMutation, useUpdateKbArticleMutation } from '../queries/kb'
import { parseApiError } from '@/utils/parseApiError'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const route = useRoute()
const { t, locale } = useI18n()
const message = useMessage()
const createKbArticleMutation = useCreateKbArticleMutation()
const updateKbArticleMutation = useUpdateKbArticleMutation()
const authStore = useAuthStore()

const isEdit = computed(() => !!route.params.id)
const articleId = computed(() => route.params.id as string | undefined)

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

const DRAFT_DEBOUNCE_MS = 7_000
const LOCAL_DRAFT_KEY = computed(() => {
  const uid = authStore.user?.id ?? 'anon'
  return isEdit.value && articleId.value
    ? `kb-draft-${uid}-${articleId.value}`
    : `kb-draft-new-${uid}`
})

interface LocalDraftPayload {
  title: string
  body: string
  section_id: string | null
  status: 'draft' | 'published'
  tags: string[]
  savedAt: number
}

let draftDebounceTimer: ReturnType<typeof setTimeout> | null = null
const showRecoveryBanner = ref(false)
const pendingLocalDraft = ref<LocalDraftPayload | null>(null)
const draftRelativeLabel = ref('')
let relativeTicker: ReturnType<typeof setInterval> | null = null
let suppressNextWatch = false

const statusOptions = computed(() => [
  { label: t('kb.status.draft'), value: 'draft' },
  { label: t('kb.status.published'), value: 'published' },
])

interface KbSectionOption {
  label: string
  key: string
  children?: KbSectionOption[]
  [k: string]: unknown
}

function sectionToOption(s: KbSection): KbSectionOption {
  return {
    label: s.title,
    key: s.id,
    children: s.children.length ? s.children.map(sectionToOption) : undefined,
  }
}

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

function getErrorStatus(err: unknown): number | undefined {
  const e = err as {
    status?: number
    statusCode?: number
    response?: { status?: number }
  } | null
  return e?.response?.status ?? e?.status ?? e?.statusCode
}

function isBodyEmpty(html: string): boolean {
  const stripped = html.replace(/<[^>]*>/g, '').replace(/&nbsp;/g, ' ').trim()
  return stripped.length === 0
}

async function onSubmit() {
  if (!form.value.title.trim()) {
    message.warning(t('kb.form.titleRequired'))
    return
  }
  if (isBodyEmpty(form.value.body)) {
    message.warning(t('kb.form.bodyRequired'))
    return
  }

  saving.value = true
  try {
    if (isEdit.value && articleId.value) {
      const updated = await updateKbArticleMutation.mutateAsync({
        id: articleId.value,
        dto: {
          title: form.value.title,
          body: form.value.body,
          section_id: form.value.section_id || null,
          status: form.value.status,
          tags: form.value.tags,
          version: currentVersion.value,
          change_comment: form.value.change_comment || undefined,
        },
      })
      if (updated?.version) currentVersion.value = updated.version
      lastSavedTitle.value = form.value.title
      lastSavedBody.value = form.value.body
      cancelDraftDebounce()
      clearLocalDraft()
      message.success(t('common.saved'))
      router.push(`/kb/articles/${articleId.value}`)
    } else {
      const created = await createKbArticleMutation.mutateAsync({
        title: form.value.title,
        body: form.value.body,
        section_id: form.value.section_id || null,
        status: form.value.status,
        tags: form.value.tags,
      })
      cancelDraftDebounce()
      clearLocalDraft()
      message.success(t('kb.articleCreated'))
      router.push(`/kb/articles/${created.id}`)
    }
  } catch (err: unknown) {
    if (getErrorStatus(err) === 409) {
      message.error(t('kb.conflictError'))
    } else {
      message.error(parseApiError(err, t))
    }
  } finally {
    saving.value = false
  }
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
      // Persistent banner — silent mode must not hide a conflict from the user,
      // иначе автосохранение тихо умирает и правки теряются при перезагрузке.
      draftConflict.value = true
      if (!opts.silent) message.error(t('kb.conflictError'))
    } else if (!opts.silent) {
      message.error(t('common.errorOccurred'))
    }
  } finally {
    savingDraft.value = false
  }
}

function reloadPage() {
  if (typeof window !== 'undefined') window.location.reload()
}

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
    window.localStorage.setItem(LOCAL_DRAFT_KEY.value, JSON.stringify(payload))
    draftSavedAt.value = new Date(payload.savedAt)
    draftRelativeLabel.value = formatRelative(draftSavedAt.value)
  } catch {
    /* ignore quota errors */
  }
}

function clearLocalDraft() {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.removeItem(LOCAL_DRAFT_KEY.value)
  } catch {
    /* ignore */
  }
}

function readLocalDraft(): LocalDraftPayload | null {
  if (typeof window === 'undefined') return null
  try {
    const raw = window.localStorage.getItem(LOCAL_DRAFT_KEY.value)
    if (!raw) return null
    const parsed = JSON.parse(raw) as LocalDraftPayload
    if (!parsed || typeof parsed !== 'object') return null
    return parsed
  } catch {
    return null
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

function cancelDraftDebounce() {
  if (draftDebounceTimer) {
    clearTimeout(draftDebounceTimer)
    draftDebounceTimer = null
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

onMounted(async () => {
  try {
    const [secRes] = await Promise.all([fetchSections()])
    sections.value = secRes.items
  } catch {
    message.error(t('common.errorOccurred'))
  }

  if (!isEdit.value) {
    const querySection = route.query.section_id
    if (typeof querySection === 'string' && querySection) {
      form.value.section_id = querySection
    }
  }

  if (isEdit.value && articleId.value) {
    try {
      const art = await fetchArticle(articleId.value)
      suppressNextWatch = true
      form.value.title = art.title
      form.value.body = art.body
      form.value.section_id = art.section_id
      form.value.status = art.status === 'archived' ? 'draft' : art.status
      form.value.tags = art.tags.map((t) => t.name)
      currentVersion.value = art.version
      lastSavedTitle.value = art.title
      lastSavedBody.value = art.body
    } catch (err: unknown) {
      if (getErrorStatus(err) === 404) {
        router.replace({ name: 'kb' })
        return
      }
      message.error(t('common.errorOccurred'))
    }
  }

  const localDraft = readLocalDraft()
  if (localDraft) {
    const differs =
      localDraft.title !== form.value.title ||
      localDraft.body !== form.value.body
    if (differs) {
      pendingLocalDraft.value = localDraft
      showRecoveryBanner.value = true
    } else {
      clearLocalDraft()
    }
  }

  relativeTicker = setInterval(() => {
    if (draftSavedAt.value) {
      draftRelativeLabel.value = formatRelative(draftSavedAt.value)
    }
  }, 5_000)
})

function handleBeforeUnload() {
  if (draftDebounceTimer) {
    writeLocalDraft()
  }
}

if (typeof window !== 'undefined') {
  window.addEventListener('beforeunload', handleBeforeUnload)
}

onUnmounted(() => {
  cancelDraftDebounce()
  if (relativeTicker) {
    clearInterval(relativeTicker)
    relativeTicker = null
  }
  if (typeof window !== 'undefined') {
    window.removeEventListener('beforeunload', handleBeforeUnload)
  }
})
</script>

<style scoped>
.form-wrap {
  max-width: 900px;
  margin: 0 auto;
}

.form-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 28px;
  flex-wrap: wrap;
}

.draft-saved {
  font-size: 13px;
  color: #4caf50;
}
.draft-saved.is-saving {
  color: var(--n-text-color-2, #888);
}
.recovery-banner {
  margin-bottom: 20px;
}
.recovery-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.form-actions {
  margin-top: 28px;
  padding-top: 20px;
  border-top: 1px solid var(--color-border);
}
</style>
