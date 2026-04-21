<template>
  <AppLayout>
    <template #header-title>
      <n-breadcrumb>
        <n-breadcrumb-item @click="router.push('/news')">{{ t('nav.news') }}</n-breadcrumb-item>
        <n-breadcrumb-item>{{ isEdit ? t('news.edit.title') : t('news.create.title') }}</n-breadcrumb-item>
      </n-breadcrumb>
    </template>

    <div class="form-wrap">
      <header class="form-head">
        <h1 class="form-head__title">
          {{ isEdit ? t('news.edit.title') : t('news.create.title') }}
        </h1>
        <div class="form-head__sub">{{ t('news.pageSub') }}</div>
      </header>

      <n-spin v-if="loadingNews" style="margin:40px auto;display:block" />

      <n-form v-else :model="form" :rules="rules" ref="formRef" label-placement="top">
        <div class="form-grid">
          <!-- Editor column -->
          <div class="form-main">
            <div class="form-card">
              <n-form-item :label="t('news.form.titleLabel')" path="title">
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
                  style="width:100%"
                />
              </n-form-item>
            </div>
          </div>

          <!-- Settings sidebar -->
          <aside class="form-side">
            <div class="form-card form-card--sticky">
              <div class="side-title">{{ t('news.form.settings') }}</div>
              <div class="side-hint">{{ t('news.form.settingsHint') }}</div>

              <n-form-item :label="t('news.form.status')">
                <n-select v-model:value="form.status" :options="statusOptions" />
              </n-form-item>

              <n-form-item :label="t('news.form.category')">
                <n-input
                  v-model:value="form.category"
                  :placeholder="t('news.form.categoryPlaceholder')"
                  clearable
                />
              </n-form-item>

              <n-form-item>
                <n-checkbox v-model:checked="form.is_pinned">
                  <n-icon class="pin-icon" size="14"><StarOutline /></n-icon>
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

              <div class="side-actions">
                <n-button block :loading="saving" @click="saveAsDraft">
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
                <n-button text block @click="router.back()">
                  {{ t('common.cancel') }}
                </n-button>
              </div>

              <div v-if="lastSaved" class="autosave-hint">
                <n-icon size="13"><CheckmarkCircleOutline /></n-icon>
                {{ t('news.form.autosaved', { time: lastSaved }) }}
              </div>
            </div>
          </aside>
        </div>
      </n-form>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  NForm, NFormItem, NInput, NButton, NSpin,
  NBreadcrumb, NBreadcrumbItem, NSelect, NCheckbox, NDatePicker,
  NIcon, useMessage,
} from 'naive-ui'
import { StarOutline, CheckmarkCircleOutline } from '@vicons/ionicons5'
import AppLayout from '../components/AppLayout.vue'
import RichEditor from '../components/RichEditor.vue'
import { fetchNewsById, createNews, updateNews, saveDraft } from '../api/news'

const route = useRoute()
const router = useRouter()
const { t, locale } = useI18n()
const message = useMessage()

const isEdit = computed(() => !!route.params.id)
const newsId = computed(() => route.params.id as string | undefined)

const formRef = ref()
const loadingNews = ref(false)
const saving = ref(false)
const lastSaved = ref('')

const form = ref({
  title: '',
  body: '',
  status: 'draft' as 'draft' | 'published',
  is_pinned: false,
  category: null as string | null,
  publish_at: null as string | null,
})

const publishAtMs = computed({
  get: () => form.value.publish_at ? new Date(form.value.publish_at).getTime() : null,
  set: (ms: number | null) => { form.value.publish_at = ms ? new Date(ms).toISOString() : null },
})

const statusOptions = computed(() => [
  { label: t('news.status.draft'), value: 'draft' },
  { label: t('news.status.published'), value: 'published' },
])

const rules = {
  title: [{ required: true, message: t('news.form.required'), trigger: 'blur' }],
}

let autoSaveTimer: ReturnType<typeof setInterval> | null = null

onMounted(async () => {
  if (isEdit.value && newsId.value) {
    loadingNews.value = true
    try {
      const news = await fetchNewsById(newsId.value)
      form.value.title = news.title
      form.value.body = news.body
      form.value.status = news.status as 'draft' | 'published'
      form.value.is_pinned = news.is_pinned
      form.value.category = news.category
      form.value.publish_at = news.publish_at
    } finally {
      loadingNews.value = false
    }
  }

  autoSaveTimer = setInterval(async () => {
    if (isEdit.value && newsId.value && form.value.status === 'draft') {
      try {
        await saveDraft(newsId.value, { title: form.value.title, body: form.value.body })
        const lang = locale.value === 'ru' ? 'ru-RU' : 'en-US'
        lastSaved.value = new Date().toLocaleTimeString(lang, { hour: '2-digit', minute: '2-digit' })
      } catch { /* ignore */ }
    }
  }, 30_000)
})

onUnmounted(() => { if (autoSaveTimer) clearInterval(autoSaveTimer) })

async function saveAsDraft() {
  saving.value = true
  try {
    const data = { ...form.value, status: 'draft' as const }
    if (isEdit.value && newsId.value) {
      await updateNews(newsId.value, data)
    } else {
      const created = await createNews(data)
      router.replace(`/news/${created.id}/edit`)
    }
    message.success(t('common.save'))
  } catch {
    message.error(t('errors.generic'))
  } finally {
    saving.value = false
  }
}

async function publish() {
  saving.value = true
  try {
    const data = { ...form.value, status: 'published' as const }
    if (isEdit.value && newsId.value) {
      await updateNews(newsId.value, data)
    } else {
      await createNews(data)
    }
    message.success(t('news.create.submit'))
    router.push('/news')
  } catch {
    message.error(t('errors.generic'))
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
.form-head__title {
  margin: 0;
  font-size: 26px;
  font-weight: 800;
  letter-spacing: -0.02em;
  color: var(--color-text);
}
.form-head__sub {
  margin-top: 4px;
  color: var(--color-text-muted);
  font-size: 14px;
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

@media (max-width: 1100px) {
  .form-grid { grid-template-columns: 1fr; }
  .form-card--sticky { position: static; }
}
</style>
