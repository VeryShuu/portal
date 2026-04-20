<template>
  <AppLayout>
    <template #header-title>
      <n-breadcrumb>
        <n-breadcrumb-item @click="router.push('/news')">{{ t('nav.news') }}</n-breadcrumb-item>
        <n-breadcrumb-item>{{ isEdit ? t('news.edit.title') : t('news.create.title') }}</n-breadcrumb-item>
      </n-breadcrumb>
    </template>

    <div class="form-wrap">
      <n-spin v-if="loadingNews" style="margin:40px auto;display:block" />

      <n-form v-else :model="form" :rules="rules" ref="formRef" label-placement="top">
        <n-grid :x-gap="16" :cols="3" item-responsive responsive="screen">
          <n-grid-item span="3 m:2">
            <n-form-item :label="t('news.create.placeholder')" path="title">
              <n-input v-model:value="form.title" :placeholder="t('news.create.placeholder')" size="large" />
            </n-form-item>

            <n-form-item :label="t('news.create.bodyPlaceholder')">
              <RichEditor
                v-model="form.body"
                :placeholder="t('news.create.bodyPlaceholder')"
                style="width:100%"
              />
            </n-form-item>
          </n-grid-item>

          <n-grid-item span="3 m:1">
            <n-form-item :label="t('news.status.draft')">
              <n-select v-model:value="form.status" :options="statusOptions" />
            </n-form-item>

            <n-form-item label="Категория">
              <n-input v-model:value="form.category" clearable />
            </n-form-item>

            <n-form-item>
              <n-checkbox v-model:checked="form.is_pinned">{{ t('news.pinned') }}</n-checkbox>
            </n-form-item>

            <n-form-item :label="t('news.create.scheduleAt')">
              <n-date-picker v-model:value="publishAtMs" type="datetime" clearable style="width:100%" />
            </n-form-item>
          </n-grid-item>
        </n-grid>

        <div class="actions">
          <n-button @click="router.back()">{{ t('common.cancel') }}</n-button>
          <n-button :loading="saving" @click="saveAsDraft">{{ t('news.create.saveDraft') }}</n-button>
          <n-button type="primary" :loading="saving" @click="publish">{{ t('news.create.submit') }}</n-button>
        </div>

        <div v-if="lastSaved" class="autosave-hint">Автосохранено {{ lastSaved }}</div>
      </n-form>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  NForm, NFormItem, NInput, NButton, NSpin, NGrid, NGridItem,
  NBreadcrumb, NBreadcrumbItem, NSelect, NCheckbox, NDatePicker,
  useMessage,
} from 'naive-ui'
import AppLayout from '../components/AppLayout.vue'
import RichEditor from '../components/RichEditor.vue'
import { fetchNewsById, createNews, updateNews, saveDraft } from '../api/news'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
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

const statusOptions = [
  { label: t('news.status.draft'), value: 'draft' },
  { label: t('news.status.published'), value: 'published' },
]

const rules = {
  title: [{ required: true, message: 'Обязательное поле', trigger: 'blur' }],
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
        lastSaved.value = new Date().toLocaleTimeString('ru-RU')
      } catch {}
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
.form-wrap { max-width: 1100px; margin: 0 auto; }
.actions { display: flex; gap: 12px; justify-content: flex-end; margin-top: 24px; }
.autosave-hint { text-align: right; font-size: 12px; color: #aaa; margin-top: 8px; }
</style>
