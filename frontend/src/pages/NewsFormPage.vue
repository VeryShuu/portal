<template>
  <div class="form-wrap">
    <header class="form-head">
      <h1 class="u-page-head__title">
        {{ isEdit ? t('news.edit.title') : t('news.create.title') }}
      </h1>
      <div class="u-page-head__sub">
        {{ t('news.pageSub') }}
      </div>
    </header>

    <n-spin
      v-if="loadingNews"
      style="margin:40px auto;display:block"
    />

    <n-form
      v-else
      ref="formRef"
      :model="form"
      :rules="rules"
      label-placement="top"
    >
      <div class="form-grid">
        <div class="form-main">
          <div class="form-card">
            <n-form-item
              :label="t('news.form.titleLabel')"
              path="title"
            >
              <n-input
                v-model:value="form.title"
                :placeholder="t('news.create.placeholder')"
                size="large"
              />
            </n-form-item>

            <n-form-item :label="t('news.form.bodyLabel')">
              <RichEditor
                v-model="form.body"
                :placeholder="t('news.create.bodyPlaceholder')"
                :upload-endpoint="newsId ? `/api/v1/news/${newsId}/inline-media` : undefined"
                style="width:100%"
              />
            </n-form-item>
          </div>

          <NewsGalleryPanel :news-id="newsId" />
          <NewsAttachmentsPanel :news-id="newsId" />
          <NewsPollPanel
            :news-id="newsId"
            :has-poll="editNewsData?.has_poll"
          />
        </div>

        <aside class="form-side">
          <div class="form-card form-card--sticky">
            <div class="side-title">
              {{ t('news.form.coverImage') }}
            </div>

            <NewsCoverUpload
              :news-id="newsId"
              :is-edit="isEdit"
              :cover-image-url="coverImageUrl"
              :focal-point="form.cover_focal_point"
              :max-size-mb="coverMaxSizeMb"
              @update:cover-image-url="coverImageUrl = $event"
              @update:focal-point="form.cover_focal_point = $event"
            />

            <div class="side-divider" />

            <div class="side-title">
              {{ t('news.form.settings') }}
            </div>
            <div class="side-hint">
              {{ t('news.form.settingsHint') }}
            </div>

            <n-form-item :label="t('news.form.status')">
              <n-select
                v-model:value="form.status"
                :options="statusOptions"
              />
            </n-form-item>

            <n-form-item :label="t('news.form.categories')">
              <n-select
                v-model:value="form.categories"
                :options="categoryOptions"
                :placeholder="t('news.form.categoriesPlaceholder')"
                multiple
                clearable
                filterable
                tag
              />
            </n-form-item>

            <n-form-item>
              <n-checkbox v-model:checked="form.is_pinned">
                <n-icon
                  class="pin-icon"
                  size="14"
                >
                  <StarOutline />
                </n-icon>
                {{ t('news.pinned') }}
              </n-checkbox>
            </n-form-item>

            <n-form-item :label="t('news.create.scheduleAt')">
              <n-date-picker
                v-model:value="publishAtMs"
                type="datetime"
                clearable
                style="width:100%"
              />
            </n-form-item>

            <n-form-item :label="t('news.form.publishedAt')">
              <n-date-picker
                v-model:value="publishedAtMs"
                type="datetime"
                clearable
                style="width:100%"
              />
            </n-form-item>

            <div class="side-actions">
              <n-button
                block
                :loading="saving"
                @click="saveAsDraft"
              >
                {{ t('news.create.saveDraft') }}
              </n-button>
              <n-button
                block
                type="primary"
                :loading="saving"
                @click="publish"
              >
                {{ t('news.create.submit') }}
              </n-button>
              <n-button
                text
                block
                @click="router.back()"
              >
                {{ t('common.cancel') }}
              </n-button>
            </div>

            <div
              v-if="lastSaved"
              class="autosave-hint"
            >
              <n-icon size="13">
                <CheckmarkCircleOutline />
              </n-icon>
              {{ t('news.form.autosaved', { time: lastSaved }) }}
            </div>
          </div>
        </aside>
      </div>
    </n-form>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useInterval } from '../composables/useInterval'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  NForm, NFormItem, NInput, NButton, NSpin,
  NSelect, NCheckbox, NDatePicker, NIcon, useMessage,
  type SelectOption,
} from 'naive-ui'
import { StarOutline, CheckmarkCircleOutline } from '@vicons/ionicons5'
import RichEditor from '../components/RichEditor.vue'
import NewsCoverUpload from '../components/NewsCoverUpload.vue'
import NewsGalleryPanel from '../components/NewsGalleryPanel.vue'
import NewsAttachmentsPanel from '../components/NewsAttachmentsPanel.vue'
import NewsPollPanel from '../components/NewsPollPanel.vue'
import { saveDraft } from '../api/news'
import { parseApiError } from '../utils/parseApiError'
import {
  useNewsCategoriesQuery, useNewsUploadLimitsQuery, useNewsDetailQuery,
  useCreateNewsMutation, useUpdateNewsMutation,
} from '../queries/news'

const route = useRoute()
const router = useRouter()
const { t, locale } = useI18n()
const message = useMessage()

const createNewsMutation = useCreateNewsMutation()
const updateNewsMutation = useUpdateNewsMutation()

const isEdit = computed(() => !!route.params.id)
const newsId = computed(() => route.params.id as string | undefined)

const formRef = ref()
const saving = ref(false)
const autoSaveInFlight = ref(false)
const lastSaved = ref('')

type FocalPoint = 'top' | 'center' | 'bottom'
type NewsStatus = 'draft' | 'published'

const FOCAL_POINTS: readonly FocalPoint[] = ['top', 'center', 'bottom']
const NEWS_STATUSES: readonly NewsStatus[] = ['draft', 'published']

function toFocalPoint(value: unknown): FocalPoint | null {
  return typeof value === 'string' && (FOCAL_POINTS as readonly string[]).includes(value)
    ? (value as FocalPoint)
    : null
}

function toNewsStatus(value: unknown, fallback: NewsStatus = 'draft'): NewsStatus {
  return typeof value === 'string' && (NEWS_STATUSES as readonly string[]).includes(value)
    ? (value as NewsStatus)
    : fallback
}

const form = ref({
  title: '',
  body: '',
  status: 'draft' as 'draft' | 'published',
  is_pinned: false,
  categories: [] as string[],
  publish_at: null as string | null,
  published_at: null as string | null,
  cover_focal_point: null as FocalPoint | null,
})

const coverImageUrl = ref<string | null>(null)

const publishAtMs = computed({
  get: () => form.value.publish_at ? new Date(form.value.publish_at).getTime() : null,
  set: (ms: number | null) => { form.value.publish_at = ms ? new Date(ms).toISOString() : null },
})

const publishedAtMs = computed({
  get: () => form.value.published_at ? new Date(form.value.published_at).getTime() : null,
  set: (ms: number | null) => { form.value.published_at = ms ? new Date(ms).toISOString() : null },
})

const { data: categoriesData } = useNewsCategoriesQuery()
const categoryOptions = computed<SelectOption[]>(() =>
  (categoriesData.value ?? []).map(c => ({ label: c.name, value: c.name }))
)

const { data: uploadLimitsData } = useNewsUploadLimitsQuery()
const coverMaxSizeMb = computed(() => uploadLimitsData.value?.news_attachment_max_size_mb ?? 50)

const { data: editNewsData, isLoading: loadingNews } = useNewsDetailQuery(
  computed(() => isEdit.value && !!newsId.value ? newsId.value! : ''),
)

const formInitialized = ref(false)
watch(editNewsData, (news) => {
  if (news && !formInitialized.value) {
    formInitialized.value = true
    form.value.title = news.title
    form.value.body = news.body
    form.value.status = toNewsStatus(news.status)
    form.value.is_pinned = news.is_pinned
    form.value.categories = news.categories ?? []
    form.value.publish_at = news.publish_at
    form.value.published_at = news.published_at
    form.value.cover_focal_point = toFocalPoint(news.cover_focal_point)
    coverImageUrl.value = news.cover_image_url
  }
}, { immediate: true })

const statusOptions = computed(() => [
  { label: t('news.status.draft'), value: 'draft' },
  { label: t('news.status.published'), value: 'published' },
])

const rules = {
  title: [{ required: true, message: t('news.form.required'), trigger: 'blur' }],
}

useInterval(async () => {
  if (saving.value || autoSaveInFlight.value) return
  if (isEdit.value && newsId.value && form.value.status === 'draft') {
    autoSaveInFlight.value = true
    try {
      await saveDraft(newsId.value, { title: form.value.title, body: form.value.body })
      const lang = locale.value === 'ru' ? 'ru-RU' : 'en-US'
      lastSaved.value = new Date().toLocaleTimeString(lang, { hour: '2-digit', minute: '2-digit' })
    } catch { /* ignore */ } finally {
      autoSaveInFlight.value = false
    }
  }
}, 30_000, { immediate: true })

async function validateForm(): Promise<boolean> {
  const fr = formRef.value
  if (!fr) return true
  try {
    await fr.validate()
    return true
  } catch {
    return false
  }
}

async function saveAsDraft() {
  if (!(await validateForm())) return
  saving.value = true
  try {
    const data = { ...form.value, status: 'draft' as const }
    if (isEdit.value && newsId.value) {
      await updateNewsMutation.mutateAsync({ id: newsId.value, dto: data })
    } else {
      const created = await createNewsMutation.mutateAsync(data)
      if (!created?.id) throw new Error('createNews returned no id')
      router.replace(`/news/${created.id}/edit`)
    }
    message.success(t('common.save'))
  } catch (e) {
    message.error(parseApiError(e, t))
  } finally {
    saving.value = false
  }
}

async function publish() {
  if (!(await validateForm())) return
  saving.value = true
  try {
    const data = { ...form.value, status: 'published' as const }
    if (isEdit.value && newsId.value) {
      await updateNewsMutation.mutateAsync({ id: newsId.value, dto: data })
    } else {
      const created = await createNewsMutation.mutateAsync(data)
      if (!created?.id) throw new Error('createNews returned no id')
    }
    message.success(t('news.create.submit'))
    router.push('/news')
  } catch (e) {
    message.error(parseApiError(e, t))
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.form-wrap {
  max-width: 1280px;
  margin: 0 auto;
}
.form-head {
  margin-bottom: 20px;
}
.form-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 20px;
  align-items: flex-start;
}
.form-main { min-width: 0; }
.form-side { min-width: 0; }
.form-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 20px 22px;
  box-shadow: var(--shadow-sm);
  transition: border-color 0.15s, box-shadow 0.15s;
}
.form-card--sticky {
  position: sticky;
  top: 16px;
}
.side-title {
  font-size: 13px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--color-text-muted);
  margin-bottom: 4px;
}
.side-hint {
  font-size: 12px;
  color: var(--color-text-subtle);
  margin-bottom: 16px;
  line-height: 1.5;
}
.side-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 8px;
  padding-top: 14px;
  border-top: 1px solid var(--color-border);
}
.pin-icon {
  color: var(--color-brand-red);
  margin-right: 2px;
  vertical-align: -2px;
}
.autosave-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  justify-content: center;
  margin-top: 12px;
  font-size: 12px;
  color: var(--color-success);
}
.side-divider {
  height: 1px;
  background: var(--color-border);
  margin: 16px 0;
}
@media (max-width: 1100px) {
  .form-grid { grid-template-columns: 1fr; }
  .form-card--sticky { position: static; }
}
</style>
