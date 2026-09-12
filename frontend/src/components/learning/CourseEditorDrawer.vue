<template>
  <n-drawer
    class="learning-editor-drawer"
    :show="show"
    :width="drawerWidth"
    placement="right"
    @update:show="emit('update:show', $event)"
  >
    <n-drawer-content
      :title="course?.title ?? t('learning.editor.loading')"
      closable
    >
      <!-- Ревью 2026-08-30: ошибка загрузки — не пустой drawer, а alert с retry -->
      <n-alert
        v-if="show && query.isError.value"
        type="error"
        class="drawer-error"
      >
        {{ t('learning.admin.loadError') }}
        <n-button
          size="tiny"
          quaternary
          @click="query.refetch()"
        >
          {{ t('learning.page.retry') }}
        </n-button>
      </n-alert>
      <n-spin :show="query.isLoading.value">
        <template v-if="course">
          <div class="head-actions">
            <n-tag
              :type="course.status === 'published' ? 'success' : 'default'"
              size="small"
            >
              {{ course.status === 'published' ? t('learning.courses.published') : t('learning.courses.draft') }}
            </n-tag>
            <n-button
              size="tiny"
              @click="showEdit = true"
            >
              {{ t('common.edit') }}
            </n-button>
            <n-button
              size="tiny"
              :type="course.status === 'published' ? 'warning' : 'success'"
              secondary
              @click="togglePublished"
            >
              {{ course.status === 'published' ? t('learning.courses.unpublish') : t('learning.courses.publish') }}
            </n-button>
          </div>

          <div
            v-if="course.description"
            class="description rich-description"
            v-html="renderedDescription"
          />
          <p class="slug-hint">
            /learning/courses/{{ course.slug }}
          </p>

          <div class="cover-block">
            <img
              v-if="course.cover_url"
              :src="course.cover_url"
              class="cover-preview"
              :alt="t('learning.editor.cover.alt')"
            >
            <div class="cover-actions">
              <n-button
                size="small"
                :loading="uploadMut.isPending.value"
                @click="pickFile"
              >
                {{ course.cover_url
                  ? t('learning.editor.cover.replace')
                  : t('learning.editor.cover.upload') }}
              </n-button>
              <n-popconfirm
                v-if="course.cover_url"
                @positive-click="removeCover"
              >
                <template #trigger>
                  <n-button
                    size="small"
                    type="error"
                    secondary
                    :loading="deleteMut.isPending.value"
                  >
                    {{ t('learning.editor.cover.remove') }}
                  </n-button>
                </template>
                {{ t('learning.editor.cover.removeConfirm') }}
              </n-popconfirm>
            </div>
            <input
              ref="fileInput"
              type="file"
              accept="image/jpeg,image/png,image/webp,image/gif"
              class="cover-input"
              :aria-label="t('learning.editor.cover.alt')"
              @change="onFileChosen"
            >
          </div>

          <n-tabs
            type="segment"
            animated
          >
            <n-tab-pane
              name="items"
              :tab="t('learning.editor.tabs.items')"
            >
              <CourseItemsPanel
                :course-id="course.id"
                :items="course.items"
              />
            </n-tab-pane>
            <n-tab-pane
              name="participants"
              :tab="t('learning.editor.tabs.participants')"
            >
              <ParticipantsPanel
                :course-id="course.id"
                :course-status="course.status"
              />
            </n-tab-pane>
          </n-tabs>
        </template>
      </n-spin>

      <n-modal
        v-model:show="showEdit"
        preset="card"
        :title="t('learning.editor.editTitle')"
        style="max-width: 720px"
      >
        <n-form label-placement="top">
          <n-form-item
            :label="t('learning.courses.titleField')"
            required
          >
            <n-input
              v-model:value="editForm.title"
              :maxlength="255"
            />
          </n-form-item>
          <n-form-item :label="t('learning.courses.descriptionField')">
            <!-- Описание — тот же rich-редактор, что у новостей/заметок:
                 Markdown на выходе, sanitize на записи (backend). -->
            <RichEditor
              v-model="editForm.description"
              :placeholder="t('learning.courses.descriptionPlaceholder')"
            />
          </n-form-item>
          <n-form-item :label="t('learning.courses.slugField')">
            <n-input
              v-model:value="editForm.slug"
              :maxlength="140"
            />
          </n-form-item>
          <n-form-item :label="t('learning.courses.categoryField')">
            <n-select
              v-model:value="editForm.categoryId"
              :options="categoryOptions"
              :placeholder="t('learning.courses.categoryNone')"
              clearable
            />
          </n-form-item>
          <n-form-item :show-feedback="false">
            <n-checkbox v-model:checked="editForm.forAllStaff">
              {{ t('learning.courses.forAllStaff') }}
            </n-checkbox>
          </n-form-item>
          <n-alert
            v-if="editForm.forAllStaff"
            type="info"
            :show-icon="false"
          >
            {{ t('learning.courses.forAllStaffHint') }}
          </n-alert>
          <n-form-item :label="t('learning.courses.deadlineField')">
            <n-date-picker
              v-model:value="deadlineTs"
              type="datetime"
              clearable
              style="width: 100%"
            />
          </n-form-item>
        </n-form>
        <template #footer>
          <div class="modal-actions">
            <n-button @click="showEdit = false">
              {{ t('common.cancel') }}
            </n-button>
            <n-button
              type="primary"
              :loading="updateMut.isPending.value"
              @click="submitEdit"
            >
              {{ t('common.save') }}
            </n-button>
          </div>
        </template>
      </n-modal>
    </n-drawer-content>
  </n-drawer>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NAlert,
  NButton,
  NCheckbox,
  NDatePicker,
  NDrawer,
  NDrawerContent,
  NForm,
  NFormItem,
  NInput,
  NModal,
  NPopconfirm,
  NSelect,
  NSpin,
  NTabPane,
  NTabs,
  NTag,
  useMessage,
} from 'naive-ui'
import {
  useAdminCourseQuery,
  useDeleteCoverMutation,
  useSetCoursePublishedMutation,
  useCategoriesQuery,
  useUpdateCourseMutation,
  useUploadCoverMutation,
} from '../../queries/learning'
import { parseApiError } from '../../utils/parseApiError'
import { mdUnsafe as md } from '../../utils/markdown'
import { sanitizeHtmlAllowIframe } from '../../utils/sanitize'
import { useMutationErrorToasts } from '../../composables/useMutationErrorToasts'
import { useBrandingStore } from '../../stores/branding'
import RichEditor from '../RichEditor.vue'
import CourseItemsPanel from './CourseItemsPanel.vue'
import ParticipantsPanel from './ParticipantsPanel.vue'

const props = defineProps<{ show: boolean; courseId: string | null }>()
const emit = defineEmits<{ (e: 'update:show', value: boolean): void }>()

const { t } = useI18n()
const message = useMessage()
const brandingStore = useBrandingStore()

const query = useAdminCourseQuery(computed(() => (props.show ? props.courseId : null)))
const course = computed(() => query.data.value ?? null)

// превью описания в drawer'е — тем же конвейером, что у участника курса
const renderedDescription = computed(() => {
  const raw = course.value?.description
  if (!raw) return ''
  const origins: string[] = brandingStore.settings.allowed_iframe_origins ?? []
  return sanitizeHtmlAllowIframe(md.render(raw), origins)
})

// UX (2026-09-01): панель участников не влезала — расширяем до половины
// экрана, но не уже прежних 860px.
const drawerWidth = computed(() =>
  Math.min(window.innerWidth - 48, Math.max(860, Math.round(window.innerWidth / 2))),
)

watch(() => query.error.value, (e) => { if (e) message.error(parseApiError(e, t)) })
watch(() => query.data.value, (c) => {
  if (c) {
    editForm.value = {
      title: c.title,
      description: c.description ?? '',
      slug: c.slug,
      categoryId: c.category_id ?? null,
      forAllStaff: c.for_all_staff ?? false,
    }
    deadlineTs.value = c.deadline_at ? Date.parse(c.deadline_at) : null
    initialDeadlineTs.value = deadlineTs.value
  }
})

const showEdit = ref(false)
const editForm = ref({
  title: '',
  description: '',
  slug: '',
  categoryId: null as string | null,
  forAllStaff: false,
})

// справочник категорий (миграция 109)
const categoriesQuery = useCategoriesQuery()
const categoryOptions = computed(() =>
  (categoriesQuery.data.value ?? []).map((c) => ({ label: c.title, value: c.id })),
)
// NDatePicker работает с timestamp (number|null); в API уходит ISO/null.
const deadlineTs = ref<number | null>(null)
const initialDeadlineTs = ref<number | null>(null)
const updateMut = useUpdateCourseMutation()
const publishMut = useSetCoursePublishedMutation()

// ── обложка (этап 2, ТЗ §6.2) ────────────────────────────────────────────────
const fileInput = ref<HTMLInputElement | null>(null)
const uploadMut = useUploadCoverMutation()
const deleteMut = useDeleteCoverMutation()

useMutationErrorToasts([uploadMut.error, deleteMut.error, updateMut.error, publishMut.error], (text) => message.error(text), t)

function pickFile() {
  fileInput.value?.click()
}

async function onFileChosen(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = '' // повторный выбор того же файла тоже должен поднять change
  if (!file || !course.value) return
  try {
    await uploadMut.mutateAsync({ courseId: course.value.id, file })
    message.success(t('learning.editor.cover.uploaded'))
  } catch {
    // ошибка уже показана в watch
  }
}

async function removeCover() {
  if (!course.value) return
  try {
    await deleteMut.mutateAsync({ courseId: course.value.id })
  } catch {
    // ошибка уже показана в watch
  }
}


async function submitEdit() {
  if (!props.courseId || !editForm.value.title.trim()) return
  try {
    // deadline_at уходит в тело только при изменении: null = снять дедлайн,
    // неизменённое поле не должно случайно его обнулить.
    const deadlineChanged = deadlineTs.value !== initialDeadlineTs.value
    await updateMut.mutateAsync({
      courseId: props.courseId,
      body: {
        title: editForm.value.title.trim(),
        description: editForm.value.description.trim() || null,
        slug: editForm.value.slug.trim() || null,
        category_id: editForm.value.categoryId,
        for_all_staff: editForm.value.forAllStaff,
        ...(deadlineChanged
          ? { deadline_at: deadlineTs.value ? new Date(deadlineTs.value).toISOString() : null }
          : {}),
      },
    })
    message.success(t('common.saved'))
    showEdit.value = false
  } catch {
    // ошибка уже показана в watch
  }
}

async function togglePublished() {
  if (!course.value) return
  try {
    await publishMut.mutateAsync({
      courseId: course.value.id,
      published: course.value.status !== 'published',
    })
  } catch {
    // ошибка уже показана в watch
  }
}
</script>

<style scoped>
.head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.description {
  margin: 0 0 8px;
}

.rich-description {
  color: var(--color-text);
  font-size: 14px;
  line-height: 1.7;
  overflow-wrap: anywhere;
}

.rich-description :deep(p) {
  margin: 0 0 10px;
}

.rich-description :deep(p:last-child) {
  margin-bottom: 0;
}

.rich-description :deep(h2),
.rich-description :deep(h3),
.rich-description :deep(h4) {
  margin: 14px 0 8px;
  font-size: 15px;
  font-weight: 650;
}

.rich-description :deep(ul),
.rich-description :deep(ol) {
  margin: 0 0 10px;
  padding-left: 20px;
}

.rich-description :deep(a) {
  color: var(--color-brand-sky);
}

.rich-description :deep(img) {
  max-width: 100%;
  border-radius: var(--radius-md);
}

.slug-hint {
  color: var(--text-secondary, #999);
  font-size: 12px;
  margin: 0 0 16px;
}

.cover-block {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  margin-bottom: 16px;
}

.cover-preview {
  max-width: 240px;
  max-height: 110px;
  border-radius: 8px;
  border: 1px solid var(--border-color, #e5e5e5);
  object-fit: cover;
}

.cover-actions {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.cover-input {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
