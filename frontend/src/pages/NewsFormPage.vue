<template>
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

            <!-- Gallery -->
            <div
              class="form-card"
              style="margin-top:16px"
              :class="{ 'form-card--dropping': galleryDropping && !!newsId }"
              @dragover.prevent="onGalleryCardDragOver"
              @dragleave="onGalleryCardDragLeave"
              @drop.prevent="onGalleryCardDrop"
            >
              <div class="side-title">{{ t('news.gallery.title') }}</div>
              <div class="side-hint" v-if="!newsId" style="color:var(--color-warning,#f0a020)">{{ t('news.form.saveFirst') }}</div>
              <div class="side-hint" v-else>{{ t('news.gallery.hint') }}</div>

              <div class="gallery-grid" v-if="galleryImages.length">
                <div
                  v-for="(img, idx) in galleryImages"
                  :key="img.id"
                  class="gallery-item"
                  :class="{ 'gallery-item--drag-over': dragOverIdx === idx }"
                  draggable="true"
                  @dragstart="onGalleryDragStart(idx)"
                  @dragover.prevent="dragOverIdx = idx"
                  @dragleave="dragOverIdx = null"
                  @drop.prevent="onGalleryDrop(idx)"
                >
                  <img :src="img.url" :alt="img.original_name" class="gallery-item__img" />
                  <div class="gallery-item__overlay">
                    <n-button
                      size="tiny"
                      type="error"
                      ghost
                      circle
                      :loading="deletingGalleryId === img.id"
                      @click="handleGalleryDelete(img.id)"
                    >
                      <template #icon><n-icon><TrashOutline /></n-icon></template>
                    </n-button>
                  </div>
                  <div class="gallery-item__drag-handle">⠿</div>
                </div>
              </div>

              <n-upload
                accept="image/jpeg,image/png,image/webp,image/gif"
                :show-file-list="false"
                :custom-request="handleGalleryUpload"
                :disabled="galleryUploading || !newsId"
                multiple
              >
                <n-button size="small" :loading="galleryUploading" :disabled="!newsId" style="margin-top:10px">
                  <template #icon><n-icon><ImageOutline /></n-icon></template>
                  {{ t('news.gallery.upload') }}
                </n-button>
              </n-upload>
            </div>

            <!-- Attachments -->
            <div
              class="form-card"
              style="margin-top:16px"
              :class="{ 'form-card--dropping': attDropping && !!newsId }"
              @dragover.prevent="onAttCardDragOver"
              @dragleave="onAttCardDragLeave"
              @drop.prevent="onAttCardDrop"
            >
              <div class="side-title">{{ t('news.attachments.title') }}</div>
              <div class="side-hint" v-if="!newsId" style="color:var(--color-warning,#f0a020)">{{ t('news.form.saveFirst') }}</div>
              <div class="side-hint" v-else>{{ t('news.attachments.hint') }}</div>

              <div class="att-list" v-if="attachments.length">
                <div v-for="att in attachments" :key="att.id" class="att-item">
                  <div class="att-item__name">{{ att.original_name }}</div>
                  <div class="att-item__size">{{ formatSize(att.file_size) }}</div>
                  <n-button
                    size="tiny"
                    type="error"
                    ghost
                    :loading="deletingAttId === att.id"
                    @click="handleAttachmentDelete(att.id)"
                  >
                    <template #icon><n-icon><TrashOutline /></n-icon></template>
                  </n-button>
                </div>
              </div>

              <n-upload
                :show-file-list="false"
                :custom-request="handleAttachmentUpload"
                :disabled="attUploading || !newsId"
                multiple
              >
                <n-button size="small" :loading="attUploading" :disabled="!newsId" style="margin-top:10px">
                  <template #icon><n-icon><AttachOutline /></n-icon></template>
                  {{ t('news.attachments.upload') }}
                </n-button>
              </n-upload>
            </div>
          </div>

          <!-- Settings sidebar -->
          <aside class="form-side">
            <div class="form-card form-card--sticky">
              <div class="side-title">{{ t('news.form.coverImage') }}</div>

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

              <div class="side-title">{{ t('news.form.settings') }}</div>
              <div class="side-hint">{{ t('news.form.settingsHint') }}</div>

              <n-form-item :label="t('news.form.status')">
                <n-select v-model:value="form.status" :options="statusOptions" />
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

              <n-form-item :label="t('news.form.publishedAt')">
                <n-date-picker
                  v-model:value="publishedAtMs"
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
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useQueryClient } from '@tanstack/vue-query'
import {
  NForm, NFormItem, NInput, NButton, NSpin,
  NSelect, NCheckbox, NDatePicker,
  NIcon, useMessage, NUpload, type UploadCustomRequestOptions,
  type SelectOption,
} from 'naive-ui'
import { StarOutline, CheckmarkCircleOutline, TrashOutline, AttachOutline } from '@vicons/ionicons5'
import RichEditor from '../components/RichEditor.vue'
import NewsCoverUpload from '../components/NewsCoverUpload.vue'
import {
  createNews, updateNews, saveDraft,
  uploadGalleryImage, deleteGalleryImage, reorderGallery,
  uploadAttachment, deleteAttachment,
  type GalleryImage, type NewsAttachment,
} from '../api/news'
import { parseApiError } from '../utils/parseApiError'
import {
  useNewsCategoriesQuery, useNewsUploadLimitsQuery,
  useNewsDetailQuery, useNewsGalleryQuery, useNewsAttachmentsQuery,
} from '../queries/news'
import { queryKeys } from '../queries/keys'



const route = useRoute()
const router = useRouter()
const { t, locale } = useI18n()
const message = useMessage()

const queryClient = useQueryClient()

const isEdit = computed(() => !!route.params.id)
const newsId = computed(() => route.params.id as string | undefined)

const formRef = ref()
const saving = ref(false)
const lastSaved = ref('')

type FocalPoint = 'top' | 'center' | 'bottom'

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

const galleryImages = ref<GalleryImage[]>([])
const galleryUploading = ref(false)
const deletingGalleryId = ref<string | null>(null)
const dragStartIdx = ref<number | null>(null)
const dragOverIdx = ref<number | null>(null)
const galleryDropping = ref(false)

const attachments = ref<NewsAttachment[]>([])
const attUploading = ref(false)
const deletingAttId = ref<string | null>(null)
const attDropping = ref(false)

const publishAtMs = computed({
  get: () => form.value.publish_at ? new Date(form.value.publish_at).getTime() : null,
  set: (ms: number | null) => { form.value.publish_at = ms ? new Date(ms).toISOString() : null },
})

const publishedAtMs = computed({
  get: () => form.value.published_at ? new Date(form.value.published_at).getTime() : null,
  set: (ms: number | null) => { form.value.published_at = ms ? new Date(ms).toISOString() : null },
})

const { data: categoriesData } = useNewsCategoriesQuery()
const categories = computed(() => (categoriesData.value ?? []).map(c => c.name))
const categoryOptions = computed<SelectOption[]>(() =>
  categories.value.map(c => ({ label: c, value: c }))
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
    form.value.status = news.status as 'draft' | 'published'
    form.value.is_pinned = news.is_pinned
    form.value.categories = news.categories ?? []
    form.value.publish_at = news.publish_at
    form.value.published_at = news.published_at
    form.value.cover_focal_point = (news.cover_focal_point as FocalPoint | null) ?? null
    coverImageUrl.value = news.cover_image_url
  }
}, { immediate: true })

const { data: editGalleryData } = useNewsGalleryQuery(
  computed(() => newsId.value ?? ''),
  { enabled: computed(() => isEdit.value && !!newsId.value) },
)
watch(editGalleryData, (gallery) => {
  if (gallery && !formInitialized.value) galleryImages.value = gallery
}, { immediate: true })

const { data: editAttachmentsData } = useNewsAttachmentsQuery(
  computed(() => newsId.value ?? ''),
  { enabled: computed(() => isEdit.value && !!newsId.value) },
)
watch(editAttachmentsData, (atts) => {
  if (atts && !formInitialized.value) attachments.value = atts
}, { immediate: true })

const statusOptions = computed(() => [
  { label: t('news.status.draft'), value: 'draft' },
  { label: t('news.status.published'), value: 'published' },
])

const rules = {
  title: [{ required: true, message: t('news.form.required'), trigger: 'blur' }],
}

let autoSaveTimer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  autoSaveTimer = setInterval(async () => {
    // P1-26: skip autosave while a manual save (Опубликовать / Сохранить) is in
    // flight, otherwise both PUT requests can race and overwrite each other.
    if (saving.value) return
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

async function handleGalleryUpload(options: UploadCustomRequestOptions) {
  const { file, onFinish, onError } = options
  if (!newsId.value || !file.file) { onError(); return }
  galleryUploading.value = true
  try {
    const img = await uploadGalleryImage(newsId.value, file.file)
    galleryImages.value.push(img)
    queryClient.invalidateQueries({ queryKey: queryKeys.news.gallery(newsId.value) })
    onFinish()
  } catch (e) {
    message.error(parseApiError(e, t))
    onError()
  } finally {
    galleryUploading.value = false
  }
}

async function handleGalleryDelete(imgId: string) {
  if (!newsId.value) return
  deletingGalleryId.value = imgId
  try {
    await deleteGalleryImage(newsId.value, imgId)
    galleryImages.value = galleryImages.value.filter(i => i.id !== imgId)
    queryClient.invalidateQueries({ queryKey: queryKeys.news.gallery(newsId.value) })
  } catch (e) {
    message.error(parseApiError(e, t))
  } finally {
    deletingGalleryId.value = null
  }
}

function onGalleryDragStart(idx: number) {
  dragStartIdx.value = idx
}

async function onGalleryDrop(targetIdx: number) {
  if (dragStartIdx.value === null || dragStartIdx.value === targetIdx) {
    dragStartIdx.value = null
    dragOverIdx.value = null
    return
  }
  const arr = [...galleryImages.value]
  const [moved] = arr.splice(dragStartIdx.value, 1)
  arr.splice(targetIdx, 0, moved)
  galleryImages.value = arr.map((img, i) => ({ ...img, sort_order: i }))
  dragStartIdx.value = null
  dragOverIdx.value = null
  if (newsId.value) {
    try {
      await reorderGallery(newsId.value, galleryImages.value.map((img, i) => ({ id: img.id, sort_order: i })))
      queryClient.invalidateQueries({ queryKey: queryKeys.news.gallery(newsId.value) })
    } catch { /* silent */ }
  }
}

const GALLERY_ACCEPT = ['image/jpeg', 'image/png', 'image/webp', 'image/gif']

function onGalleryCardDragOver(e: DragEvent) {
  if (!newsId.value) return
  if (e.dataTransfer?.types.includes('Files')) {
    galleryDropping.value = true
  }
}

function onGalleryCardDragLeave(e: DragEvent) {
  const card = e.currentTarget as HTMLElement
  if (!card.contains(e.relatedTarget as Node)) {
    galleryDropping.value = false
  }
}

async function onGalleryCardDrop(e: DragEvent) {
  galleryDropping.value = false
  if (!newsId.value) return
  const files = Array.from(e.dataTransfer?.files ?? []).filter(f => GALLERY_ACCEPT.includes(f.type))
  if (!files.length) return
  galleryUploading.value = true
  try {
    for (const file of files) {
      const img = await uploadGalleryImage(newsId.value, file)
      galleryImages.value.push(img)
    }
    queryClient.invalidateQueries({ queryKey: queryKeys.news.gallery(newsId.value) })
  } catch (e) {
    message.error(parseApiError(e, t))
  } finally {
    galleryUploading.value = false
  }
}

function onAttCardDragOver(e: DragEvent) {
  if (!newsId.value) return
  if (e.dataTransfer?.types.includes('Files')) {
    attDropping.value = true
  }
}

function onAttCardDragLeave(e: DragEvent) {
  const card = e.currentTarget as HTMLElement
  if (!card.contains(e.relatedTarget as Node)) {
    attDropping.value = false
  }
}

async function onAttCardDrop(e: DragEvent) {
  attDropping.value = false
  if (!newsId.value) return
  const files = Array.from(e.dataTransfer?.files ?? [])
  if (!files.length) return
  attUploading.value = true
  try {
    for (const file of files) {
      const att = await uploadAttachment(newsId.value, file)
      attachments.value.push(att)
    }
    queryClient.invalidateQueries({ queryKey: queryKeys.news.attachments(newsId.value) })
  } catch (e) {
    message.error(parseApiError(e, t))
  } finally {
    attUploading.value = false
  }
}

async function handleAttachmentUpload(options: UploadCustomRequestOptions) {
  const { file, onFinish, onError } = options
  if (!newsId.value || !file.file) { onError(); return }
  attUploading.value = true
  try {
    const att = await uploadAttachment(newsId.value, file.file)
    attachments.value.push(att)
    queryClient.invalidateQueries({ queryKey: queryKeys.news.attachments(newsId.value) })
    onFinish()
  } catch (e) {
    message.error(parseApiError(e, t))
    onError()
  } finally {
    attUploading.value = false
  }
}

async function handleAttachmentDelete(attId: string) {
  if (!newsId.value) return
  deletingAttId.value = attId
  try {
    await deleteAttachment(newsId.value, attId)
    attachments.value = attachments.value.filter(a => a.id !== attId)
    queryClient.invalidateQueries({ queryKey: queryKeys.news.attachments(newsId.value) })
  } catch (e) {
    message.error(parseApiError(e, t))
  } finally {
    deletingAttId.value = null
  }
}

function formatSize(bytes: number | null): string {
  if (!bytes) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

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

function invalidateNewsCache(id?: string) {
  queryClient.invalidateQueries({ queryKey: queryKeys.news.all, refetchType: 'all' })
  if (id) queryClient.invalidateQueries({ queryKey: queryKeys.news.detail(id), refetchType: 'all' })
}

async function saveAsDraft() {
  if (!(await validateForm())) return
  saving.value = true
  try {
    const data = { ...form.value, status: 'draft' as const }
    if (isEdit.value && newsId.value) {
      await updateNews(newsId.value, data)
      invalidateNewsCache(newsId.value)
    } else {
      const created = await createNews(data)
      invalidateNewsCache(created.id)
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
      await updateNews(newsId.value, data)
      invalidateNewsCache(newsId.value)
    } else {
      const created = await createNews(data)
      invalidateNewsCache(created.id)
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
  transition: border-color 0.15s, box-shadow 0.15s;
}
.form-card--sticky {
  position: sticky;
  top: 16px;
}
.form-card--dropping {
  border-color: var(--color-brand-sky, #0ea5e9);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--color-brand-sky, #0ea5e9) 20%, transparent);
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


.gallery-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 8px;
  margin-bottom: 4px;
}

.gallery-item {
  position: relative;
  border-radius: var(--radius-sm);
  overflow: hidden;
  aspect-ratio: 4 / 3;
  cursor: grab;
  border: 2px solid transparent;
  transition: border-color 0.15s;
}

.gallery-item--drag-over {
  border-color: var(--color-brand-sky);
}

.gallery-item:active { cursor: grabbing; }

.gallery-item__img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.gallery-item__overlay {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.15s;
}

.gallery-item:hover .gallery-item__overlay { opacity: 1; }

.gallery-item__drag-handle {
  position: absolute;
  top: 4px;
  left: 6px;
  color: rgba(255, 255, 255, 0.8);
  font-size: 16px;
  line-height: 1;
  pointer-events: none;
}

.att-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 4px;
}

.att-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  background: var(--color-bg-muted);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
}

.att-item__name {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.att-item__size {
  font-size: 12px;
  color: var(--color-text-muted);
  white-space: nowrap;
}

@media (max-width: 1100px) {
  .form-grid { grid-template-columns: 1fr; }
  .form-card--sticky { position: static; }
}
</style>
