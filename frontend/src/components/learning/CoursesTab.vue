<template>
  <section>
    <div class="toolbar">
      <n-input
        v-model:value="search"
        :placeholder="t('learning.courses.searchPlaceholder')"
        clearable
        style="max-width: 320px"
      />
      <n-button
        type="primary"
        @click="showCreate = true"
      >
        <template #icon>
          <n-icon><AddOutline /></n-icon>
        </template>
        {{ t('learning.courses.create') }}
      </n-button>
    </div>

    <n-data-table
      :columns="columns"
      :data="rows"
      :loading="query.isLoading.value"
      :row-key="(c: LearningCourse) => c.id"
      :bordered="false"
      striped
      :scroll-x="790"
    />

    <n-pagination
      v-if="total > pageSize"
      class="pager"
      :page="page"
      :page-size="pageSize"
      :item-count="total"
      @update:page="onPage"
    />

    <n-modal
      v-model:show="showCreate"
      class="learning-course-modal"
      preset="card"
      :title="t('learning.courses.createTitle')"
      style="max-width: 720px"
    >
      <n-form label-placement="top">
        <n-form-item
          :label="t('learning.courses.titleField')"
          required
        >
          <n-input
            v-model:value="form.title"
            :maxlength="255"
          />
        </n-form-item>
        <n-form-item :label="t('learning.courses.descriptionField')">
          <!-- Описание — тот же rich-редактор, что у новостей/заметок:
               Markdown на выходе, sanitize на записи (backend). -->
          <RichEditor
            v-model="form.description"
            :placeholder="t('learning.courses.descriptionPlaceholder')"
          />
        </n-form-item>
        <n-form-item :label="t('learning.courses.slugField')">
          <n-input
            v-model:value="form.slug"
            :maxlength="140"
            :placeholder="t('learning.courses.slugAuto')"
          />
        </n-form-item>
        <n-form-item :label="t('learning.courses.categoryField')">
          <n-select
            v-model:value="form.categoryId"
            :options="categoryOptions"
            :placeholder="t('learning.courses.categoryNone')"
            clearable
          />
        </n-form-item>
        <n-form-item :show-feedback="false">
          <n-checkbox v-model:checked="form.forAllStaff">
            {{ t('learning.courses.forAllStaff') }}
          </n-checkbox>
        </n-form-item>
        <n-alert
          v-if="form.forAllStaff"
          type="info"
          :show-icon="false"
        >
          {{ t('learning.courses.forAllStaffHint') }}
        </n-alert>
      </n-form>
      <template #footer>
        <div class="modal-actions">
          <n-button @click="showCreate = false">
            {{ t('common.cancel') }}
          </n-button>
          <n-button
            type="primary"
            :loading="createMut.isPending.value"
            @click="submitCreate"
          >
            {{ t('common.create') }}
          </n-button>
        </div>
      </template>
    </n-modal>

    <CourseEditorDrawer
      v-model:show="editorOpen"
      :course-id="selectedId"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, h, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NAlert,
  NButton,
  NCheckbox,
  NDataTable,
  NForm,
  NFormItem,
  NIcon,
  NInput,
  NModal,
  NPagination,
  NPopconfirm,
  NSelect,
  NTag,
  useMessage,
  type DataTableColumns,
} from 'naive-ui'
import { AddOutline, TrashOutline } from '@vicons/ionicons5'
import {
  useAdminCoursesQuery,
  useCategoriesQuery,
  useCreateCourseMutation,
  useDeleteCourseMutation,
  useSetCoursePublishedMutation,
} from '../../queries/learning'
import type { LearningCourse } from '../../api/learning'
import { parseApiError } from '../../utils/parseApiError'
import { useMutationErrorToasts } from '../../composables/useMutationErrorToasts'
import { useDebounceFn } from '../../composables/useDebounceFn'
import RichEditor from '../RichEditor.vue'
import CourseEditorDrawer from './CourseEditorDrawer.vue'

const { t } = useI18n()
const message = useMessage()

const search = ref('')
// Ревью 2026-08-30: запрос на каждую клавишу → дебаунс; смена запроса
// сбрасывает страницу (поиск со 2+ страницы уходил мимо выдачи).
const debouncedSearch = ref('')
const page = ref(1)
const pageSize = 20
const pushSearch = useDebounceFn((value: string) => {
  debouncedSearch.value = value
  page.value = 1
}, 300)

watch(search, (value) => pushSearch(value))

const params = computed(() => ({ q: debouncedSearch.value || undefined, limit: pageSize, offset: (page.value - 1) * pageSize }))
const query = useAdminCoursesQuery(params)
const rows = computed<LearningCourse[]>(() => query.data.value?.items ?? [])
const total = computed(() => query.data.value?.total ?? 0)

function onPage(p: number) {
  page.value = p
}

const selectedId = ref<string | null>(null)
const editorOpen = ref(false)

function openEditor(course: LearningCourse) {
  selectedId.value = course.id
  editorOpen.value = true
}

const showCreate = ref(false)
const form = ref<{
  title: string
  description: string
  slug: string
  categoryId: string | null
  forAllStaff: boolean
}>({
  title: '',
  description: '',
  slug: '',
  categoryId: null,
  forAllStaff: false,
})

// справочник категорий (миграция 109): select в форме курса
const categoriesQuery = useCategoriesQuery()
const categoryOptions = computed(() =>
  (categoriesQuery.data.value ?? []).map((c) => ({ label: c.title, value: c.id })),
)
const createMut = useCreateCourseMutation()
const publishMut = useSetCoursePublishedMutation()
const deleteMut = useDeleteCourseMutation()

watch(() => query.error.value, (e) => { if (e) message.error(parseApiError(e, t)) })
useMutationErrorToasts([createMut.error, publishMut.error, deleteMut.error], (text) => message.error(text), t)

async function submitCreate() {
  if (!form.value.title.trim()) {
    message.error(t('learning.courses.titleRequired'))
    return
  }
  try {
    await createMut.mutateAsync({
      title: form.value.title.trim(),
      description: form.value.description.trim() || null,
      slug: form.value.slug.trim() || null,
      category_id: form.value.categoryId,
      for_all_staff: form.value.forAllStaff,
    })
    message.success(t('learning.courses.created'))
    showCreate.value = false
    form.value = {
      title: '',
      description: '',
      slug: '',
      categoryId: null,
      forAllStaff: false,
    }
  } catch {
    // ошибка уже показана в watch
  }
}

async function togglePublished(course: LearningCourse) {
  try {
    await publishMut.mutateAsync({ courseId: course.id, published: course.status !== 'published' })
  } catch {
    // ошибка уже показана в watch
  }
}

async function removeCourse(course: LearningCourse) {
  try {
    await deleteMut.mutateAsync(course.id)
    message.success(t('learning.courses.deleted'))
  } catch {
    // ошибка уже показана в watch
  }
}

const columns = computed<DataTableColumns<LearningCourse>>(() => [
  // minWidth у «Название»/«Slug» + scroll-x: на узких экранах таблица скроллится
  // горизонтально, действия остаются в одну строку (2026-09-01, ревью UI).
  {
    title: t('learning.courses.colTitle'),
    key: 'title',
    minWidth: 160,
    render: (c) =>
      h('span', { class: 'course-title-cell' }, [
        h(
          'a',
          {
            href: '#',
            class: 'course-link',
            onClick: (ev: Event) => {
              ev.preventDefault()
              openEditor(c)
            },
          },
          c.title,
        ),
        // обязательный курс «для всех сотрудников» (миграция 111)
        c.for_all_staff
          ? h(
              NTag,
              { type: 'warning', size: 'small', bordered: false },
              { default: () => t('learning.courses.forAllTag') },
            )
          : null,
      ]),
  },
  { title: t('learning.courses.colSlug'), key: 'slug', minWidth: 150 },
  {
    title: t('learning.courses.colStatus'),
    key: 'status',
    width: 140,
    render: (c) =>
      h(
        NTag,
        { type: c.status === 'published' ? 'success' : 'default', size: 'small' },
        { default: () => (c.status === 'published' ? t('learning.courses.published') : t('learning.courses.draft')) },
      ),
  },
  {
    title: t('learning.courses.colActions'),
    key: 'actions',
    width: 340,
    render: (c) =>
      h('div', { class: 'row-actions' }, [
        h(
          NButton,
          { size: 'small', onClick: () => openEditor(c) },
          { default: () => t('learning.courses.open') },
        ),
        h(
          NButton,
          {
            size: 'small',
            type: c.status === 'published' ? 'warning' : 'success',
            secondary: true,
            onClick: () => togglePublished(c),
          },
          { default: () => (c.status === 'published' ? t('learning.courses.unpublish') : t('learning.courses.publish')) },
        ),
        h(
          NPopconfirm,
          { onPositiveClick: () => removeCourse(c) },
          {
            trigger: () =>
              h(
                NButton,
                { size: 'small', type: 'error', quaternary: true, loading: deleteMut.isPending.value },
                {
                  icon: () => h(NIcon, null, { default: () => h(TrashOutline) }),
                  default: () => t('common.delete'),
                },
              ),
            default: () => t('learning.courses.deleteConfirm'),
          },
        ),
      ]),
  },
])
</script>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.pager {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

:deep(.course-link) {
  color: inherit;
  font-weight: 500;
}

:deep(.row-actions) {
  display: flex;
  gap: 8px;
  /* действия курса — всегда одной строкой: на узких таблицу скроллит scroll-x */
  flex-wrap: nowrap;
}
</style>
