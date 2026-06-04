<template>
  <div class="form-wrap u-page-wrap u-page-wrap--reading">
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
        <ArticleMetaSection
          v-model:title="form.title"
          v-model:section-id="form.section_id"
          v-model:tags="form.tags"
          :section-options="sectionOptions"
        />
        <ArticleAccessSection
          v-model:status="form.status"
          v-model:change-comment="form.change_comment"
          :is-edit="isEdit"
          :status-options="statusOptions"
        />
        <ArticleContentSection
          v-model="form.body"
          :upload-endpoint="articleId ? `/api/v1/kb/articles/${articleId}/media` : undefined"
        />
        <ArticleAttachmentsSection
          :article-id="articleId"
          :is-edit="isEdit"
        />
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
import { computed, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import { NForm, NGrid, NAlert, NButton } from 'naive-ui'
import ArticleMetaSection from '../components/kb/article-form/ArticleMetaSection.vue'
import ArticleContentSection from '../components/kb/article-form/ArticleContentSection.vue'
import ArticleAccessSection from '../components/kb/article-form/ArticleAccessSection.vue'
import ArticleAttachmentsSection from '../components/kb/article-form/ArticleAttachmentsSection.vue'
import { fetchSections, fetchArticle } from '../api/kb'
import { useCreateKbArticleMutation, useUpdateKbArticleMutation } from '../queries/kb'
import { parseApiError, getErrorStatus } from '@/utils/parseApiError'
import { useAuthStore } from '../stores/auth'
import { useArticleFormState, isBodyEmpty } from './composables/useArticleFormState'

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

function reloadPage() {
  if (typeof window !== 'undefined') window.location.reload()
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
