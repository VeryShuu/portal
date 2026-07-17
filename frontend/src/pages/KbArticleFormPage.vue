<template>
  <div class="form-wrap u-page-wrap">
    <header class="editor-header">
      <div class="editor-header__titles">
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

      <div class="form-actions u-flex u-gap-12">
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
    </header>

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
      <div class="editor-layout">
        <div class="editor-main">
          <ArticleMetaSection
            v-model:title="form.title"
            :error="showValidation && titleInvalid"
            :error-text="t('kb.form.titleRequired')"
          />
          <ArticleContentSection
            v-model="form.body"
            :upload-endpoint="articleId ? `/api/v1/kb/articles/${articleId}/media` : undefined"
            :error="showValidation && bodyInvalid"
            :error-text="t('kb.form.bodyRequired')"
          />
        </div>

        <aside class="editor-aside">
          <ArticleSettingsSection
            v-model:status="form.status"
            v-model:section-id="form.section_id"
            v-model:tags="form.tags"
            v-model:change-comment="form.change_comment"
            :is-edit="isEdit"
            :status-options="statusOptions"
            :section-options="sectionOptions"
          />
          <ArticleAttachmentsSection
            :article-id="articleId"
            :is-edit="isEdit"
          />
        </aside>
      </div>
    </n-form>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import { NForm, NAlert, NButton } from 'naive-ui'
import ArticleMetaSection from '../components/kb/article-form/ArticleMetaSection.vue'
import ArticleContentSection from '../components/kb/article-form/ArticleContentSection.vue'
import ArticleSettingsSection from '../components/kb/article-form/ArticleSettingsSection.vue'
import ArticleAttachmentsSection from '../components/kb/article-form/ArticleAttachmentsSection.vue'
import { fetchSections, fetchArticle } from '../api/kb'
import { useCreateKbArticleMutation, useUpdateKbArticleMutation } from '../queries/kb'
import { parseApiError, getErrorStatus } from '@/utils/parseApiError'
import { useAuthStore } from '../stores/auth'
import { useArticleFormState, isBodyEmpty } from './composables/useArticleFormState'
import { useDirtyTracker } from '../composables/useDirtyTracker'
import { useFormLeaveGuard } from '../composables/useFormLeaveGuard'

const router = useRouter()
const route = useRoute()
const { t, locale } = useI18n()
const message = useMessage()
const createKbArticleMutation = useCreateKbArticleMutation()
const updateKbArticleMutation = useUpdateKbArticleMutation()
const authStore = useAuthStore()

const isEdit = computed(() => !!route.params.id)
const articleId = computed(() => route.params.id as string | undefined)

const LOCAL_DRAFT_KEY = computed(() => {
  const uid = authStore.user?.id ?? 'anon'
  return isEdit.value && articleId.value
    ? `kb-draft-${uid}-${articleId.value}`
    : `kb-draft-new-${uid}`
})

const {
  form,
  currentVersion,
  saving,
  savingDraft,
  draftConflict,
  sections,
  showRecoveryBanner,
  pendingLocalDraft,
  statusOptions,
  sectionOptions,
  draftIndicator,
  recoveryTimeLabel,
  onSaveDraft,
  cancelDraftDebounce,
  clearLocalDraft,
  readLocalDraft,
  applyLocalDraft,
  dismissLocalDraft,
  handleBeforeUnload,
  startRelativeTicker,
  stopRelativeTicker,
  initFromArticle,
  lastSavedTitle,
  lastSavedBody,
} = useArticleFormState({
  isEdit,
  articleId,
  localDraftKey: LOCAL_DRAFT_KEY,
  t: t as (key: string, values?: Record<string, unknown>) => string,
  locale,
  message,
})

const showValidation = ref(false)
const titleInvalid = computed(() => !form.value.title.trim())
const bodyInvalid = computed(() => isBodyEmpty(form.value.body))

const { isDirty, markPristine } = useDirtyTracker(() =>
  JSON.stringify({
    title: form.value.title,
    body: form.value.body,
    section_id: form.value.section_id,
    status: form.value.status,
    tags: form.value.tags,
  }),
)

useFormLeaveGuard({
  dirty: isDirty,
  i18nKeys: {
    title: 'kb.leave.title',
    content: 'kb.leave.content',
    confirm: 'kb.leave.confirm',
  },
})

function reloadPage() {
  if (typeof window !== 'undefined') window.location.reload()
}

async function onSubmit() {
  if (titleInvalid.value || bodyInvalid.value) {
    showValidation.value = true
    message.warning(t(titleInvalid.value ? 'kb.form.titleRequired' : 'kb.form.bodyRequired'))
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
      markPristine()
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
      markPristine()
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

onMounted(async () => {
  try {
    const secRes = await fetchSections()
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
      initFromArticle(art)
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

  startRelativeTicker()
  markPristine()
})

if (typeof window !== 'undefined') {
  window.addEventListener('beforeunload', handleBeforeUnload)
}

onUnmounted(() => {
  cancelDraftDebounce()
  stopRelativeTicker()
  if (typeof window !== 'undefined') {
    window.removeEventListener('beforeunload', handleBeforeUnload)
  }
})
</script>

<style scoped>
.editor-header {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  padding: 16px 0;
  margin-bottom: 8px;
  background: var(--color-bg);
  border-bottom: 1px solid var(--color-border);
}

.editor-header__titles {
  display: flex;
  align-items: baseline;
  gap: 14px;
  min-width: 0;
}

.editor-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  gap: 24px;
  align-items: start;
}

.editor-main {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
}

.editor-aside {
  position: sticky;
  top: 84px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

@media (max-width: 980px) {
  .editor-layout {
    grid-template-columns: minmax(0, 1fr);
  }
  .editor-aside {
    position: static;
    order: -1;
  }
}

.draft-saved {
  font-size: 13px;
  color: var(--color-success);
}
.draft-saved.is-saving {
  color: var(--color-text-subtle);
}
.recovery-banner {
  margin-bottom: 20px;
}
.recovery-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}
</style>
