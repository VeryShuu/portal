<template>
  <div class="form-wrap">
      <div class="form-header">
        <h1 class="form-title">{{ isEdit ? t('kb.editArticle') : t('kb.createArticle') }}</h1>
        <div v-if="draftSavedAt" class="draft-saved">
          ✓ {{ t('kb.draftSaved') }} {{ formatTime(draftSavedAt) }}
        </div>
      </div>

      <n-form :model="form" label-placement="top">
        <n-grid :cols="2" :x-gap="16">
          <n-gi :span="2">
            <n-form-item :label="t('kb.form.title')" required>
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
            <n-form-item :label="t('kb.form.body')" required>
              <RichEditor v-model="form.body" :placeholder="t('kb.form.bodyPlaceholder')" :upload-endpoint="articleId ? `/api/v1/kb/articles/${articleId}/media` : undefined" style="width:100%" />
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

          <n-gi v-if="isEdit && articleId" :span="2">
            <n-form-item :label="t('kb.files.title')">
              <KbAttachmentsPanel :article-id="articleId" :can-upload="true" style="width:100%" />
            </n-form-item>
          </n-gi>
        </n-grid>

        <div class="form-actions">
          <n-button @click="router.back()">{{ t('common.cancel') }}</n-button>
          <n-button
            v-if="isEdit"
            :loading="savingDraft"
            @click="onSaveDraft"
          >
            {{ t('kb.saveDraft') }}
          </n-button>
          <n-button type="primary" :loading="saving" @click="onSubmit">
            {{ isEdit ? t('common.save') : t('kb.publish') }}
          </n-button>
        </div>
      </n-form>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import {
  NForm, NFormItem, NInput, NSelect, NButton, NGrid, NGi,
  NDynamicTags, NTreeSelect,
} from 'naive-ui'
import { useQueryClient } from '@tanstack/vue-query'
import RichEditor from '../components/RichEditor.vue'
import KbAttachmentsPanel from '../components/KbAttachmentsPanel.vue'
import { fetchSections, fetchArticle, createArticle, updateArticle, saveDraft, type KbSection } from '../api/kb'
import { queryKeys } from '../queries/keys'

const router = useRouter()
const route = useRoute()
const { t, locale } = useI18n()
const message = useMessage()
const queryClient = useQueryClient()

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
const draftSavedAt = ref<Date | null>(null)
const sections = ref<KbSection[]>([])

const statusOptions = computed(() => [
  { label: t('kb.status.draft'), value: 'draft' },
  { label: t('kb.status.published'), value: 'published' },
])

function sectionToOption(s: KbSection): any {
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

async function onSubmit() {
  if (!form.value.title.trim()) {
    message.warning(t('kb.form.titleRequired'))
    return
  }

  saving.value = true
  try {
    if (isEdit.value && articleId.value) {
      await updateArticle(articleId.value, {
        title: form.value.title,
        body: form.value.body,
        section_id: form.value.section_id,
        status: form.value.status,
        tags: form.value.tags,
        version: currentVersion.value,
        change_comment: form.value.change_comment || undefined,
      })
      queryClient.invalidateQueries({ queryKey: queryKeys.kb.article(articleId.value) })
      queryClient.invalidateQueries({ queryKey: queryKeys.kb.versions(articleId.value) })
      queryClient.invalidateQueries({ queryKey: ['kb', 'articles'] })
      message.success(t('common.saved'))
      router.push(`/kb/articles/${articleId.value}`)
    } else {
      const created = await createArticle({
        title: form.value.title,
        body: form.value.body,
        section_id: form.value.section_id,
        status: form.value.status,
        tags: form.value.tags,
      })
      queryClient.invalidateQueries({ queryKey: ['kb', 'articles'] })
      queryClient.invalidateQueries({ queryKey: queryKeys.kb.tags() })
      message.success(t('kb.articleCreated'))
      router.push(`/kb/articles/${created.id}`)
    }
  } catch (err: any) {
    if (err?.response?.status === 409) {
      message.error(t('kb.conflictError'))
    } else {
      message.error(t('common.error'))
    }
  } finally {
    saving.value = false
  }
}

async function onSaveDraft() {
  if (!articleId.value) return
  if (savingDraft.value) return
  savingDraft.value = true
  try {
    await saveDraft(articleId.value, { title: form.value.title, body: form.value.body })
    draftSavedAt.value = new Date()
  } catch {
    message.error(t('common.error'))
  } finally {
    savingDraft.value = false
  }
}

let autoSaveInterval: ReturnType<typeof setInterval> | null = null

onMounted(async () => {
  try {
    const [secRes] = await Promise.all([fetchSections()])
    sections.value = secRes.items
  } catch {
    message.error(t('common.error'))
  }

  if (isEdit.value && articleId.value) {
    try {
      const art = await fetchArticle(articleId.value)
      form.value.title = art.title
      form.value.body = art.body
      form.value.section_id = art.section_id
      form.value.status = art.status === 'archived' ? 'draft' : art.status
      form.value.tags = art.tags.map((t) => t.name)
      currentVersion.value = art.version

      if (art.status === 'draft') {
        autoSaveInterval = setInterval(onSaveDraft, 30_000)
      }
    } catch (err: unknown) {
      const status = (err as { status?: number; statusCode?: number })?.status
        ?? (err as { status?: number; statusCode?: number })?.statusCode
      if (status === 404) {
        router.replace({ name: 'kb' })
      } else {
        message.error(t('common.error'))
      }
    }
  }
})

onUnmounted(() => {
  if (autoSaveInterval) clearInterval(autoSaveInterval)
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

.form-title {
  margin: 0;
  font-size: 26px;
  font-weight: 800;
  color: var(--color-text);
  letter-spacing: -0.02em;
}

.draft-saved {
  font-size: 13px;
  color: #4caf50;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 28px;
  padding-top: 20px;
  border-top: 1px solid var(--color-border);
}
</style>
