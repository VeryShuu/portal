<template>
  <section>
    <div class="panel-actions">
      <n-button
        size="small"
        @click="showAdd = true"
      >
        <template #icon>
          <n-icon><AddOutline /></n-icon>
        </template>
        {{ t('learning.items.add') }}
      </n-button>
    </div>

    <n-empty
      v-if="items.length === 0"
      :description="t('learning.items.empty')"
    />
    <div
      v-else
      class="items-list"
    >
      <div
        v-for="(item, idx) in items"
        :key="item.id"
        class="item-row"
        :class="{ 'item-row--section': item.type === 'section' }"
      >
        <div class="item-order">
          <n-button
            quaternary
            size="tiny"
            :disabled="idx === 0 || reorderMut.isPending.value"
            @click="move(idx, -1)"
          >
            <n-icon><ChevronUpOutline /></n-icon>
          </n-button>
          <n-button
            quaternary
            size="tiny"
            :disabled="idx === items.length - 1 || reorderMut.isPending.value"
            @click="move(idx, 1)"
          >
            <n-icon><ChevronDownOutline /></n-icon>
          </n-button>
        </div>

        <div class="item-main">
          <n-tag
            size="tiny"
            :bordered="false"
            :type="item.type === 'test' ? 'info' : item.type === 'section' ? 'warning' : 'default'"
          >
            {{
              item.type === 'test'
                ? t('learning.items.kindTest')
                : item.type === 'section'
                  ? t('learning.items.kindSection')
                  : t('learning.items.kindMaterial')
            }}
          </n-tag>
          <span
            class="item-title"
            :class="{ 'item-title--section': item.type === 'section' }"
            :title="item.title"
          >{{ item.title }}</span>
        </div>

        <!-- Формат — отдельная колонка фиксированной ширины: чипы PDF/Видео/
             Ссылка всегда ровно друг под другом (ревью UI 2026-09-01) -->
        <div class="item-format-slot">
          <n-tag
            v-if="formatMeta(item)"
            size="tiny"
            :bordered="false"
            class="item-format"
            :title="formatMeta(item)!.tooltip ?? undefined"
          >
            <template #icon>
              <n-icon :size="12"><component :is="formatMeta(item)!.icon" /></n-icon>
            </template>
            {{ formatMeta(item)!.label }}
          </n-tag>
        </div>

        <div class="item-actions">
          <n-button
            v-if="item.type === 'test'"
            size="tiny"
            @click="testItemId = item.id"
          >
            {{ t('learning.items.configureTest') }}
          </n-button>
          <n-button
            v-if="item.type === 'material'"
            size="tiny"
            :loading="uploadMut.isPending.value"
            @click="pickFile(item.id)"
          >
            {{ item.file_path ? t('learning.items.replaceFile') : t('learning.items.attachFile') }}
          </n-button>
          <n-button
            size="tiny"
            @click="startEdit(item)"
          >
            {{ t('common.edit') }}
          </n-button>
          <!-- Ревью 2026-08-30: деструктив — с подтверждением -->
          <n-popconfirm
            :show-icon="false"
            @positive-click="removeItem(item.id)"
          >
            <template #trigger>
              <n-button
                size="tiny"
                type="error"
                quaternary
              >
                {{ t('common.delete') }}
              </n-button>
            </template>
            {{ t('learning.items.deleteConfirm') }}
          </n-popconfirm>
        </div>
      </div>
    </div>

    <input
      ref="fileInput"
      type="file"
      accept="application/pdf"
      style="display: none"
      @change="onFilePicked"
    >

    <n-modal
      class="learning-item-modal"
      v-model:show="showAdd"
      preset="card"
      :title="t('learning.items.addTitle')"
      style="max-width: 520px"
    >
      <n-form label-placement="top">
        <n-form-item
          :label="t('learning.items.typeField')"
          required
        >
          <n-radio-group v-model:value="addForm.type">
            <n-radio value="material">
              {{ t('learning.items.kindMaterial') }}
            </n-radio>
            <n-radio value="test">
              {{ t('learning.items.kindTest') }}
            </n-radio>
            <n-radio value="section">
              {{ t('learning.items.kindSection') }}
            </n-radio>
          </n-radio-group>
        </n-form-item>
        <n-form-item
          :label="t('learning.items.titleField')"
          required
        >
          <n-input
            v-model:value="addForm.title"
            :maxlength="255"
          />
        </n-form-item>
        <n-form-item
          v-if="addForm.type === 'material'"
          :label="t('learning.items.descriptionField')"
        >
          <!-- Описание/комментарий материала — тот же rich-редактор, что у
               описания курса: Markdown на выходе, sanitize на записи. -->
          <RichEditor
            v-model="addForm.description"
            :placeholder="t('learning.items.descriptionPlaceholder')"
          />
        </n-form-item>
        <n-form-item
          v-if="addForm.type === 'material'"
          :label="t('learning.items.urlField')"
        >
          <n-input
            v-model:value="addForm.url"
            placeholder="https://"
            :maxlength="2048"
          />
        </n-form-item>
        <n-alert
          v-if="addForm.type === 'material'"
          type="info"
          :show-icon="false"
        >
          {{ t('learning.items.fileHint') }}
        </n-alert>
      </n-form>
      <template #footer>
        <div class="modal-actions">
          <n-button @click="showAdd = false">
            {{ t('common.cancel') }}
          </n-button>
          <n-button
            type="primary"
            :loading="addMut.isPending.value"
            @click="submitAdd"
          >
            {{ t('common.create') }}
          </n-button>
        </div>
      </template>
    </n-modal>

    <n-modal
      class="learning-item-modal"
      v-model:show="showEdit"
      preset="card"
      :title="t('learning.items.editTitle')"
      style="max-width: 520px"
    >
      <n-form label-placement="top">
        <n-form-item
          :label="t('learning.items.titleField')"
          required
        >
          <n-input
            v-model:value="editForm.title"
            :maxlength="255"
          />
        </n-form-item>
        <n-form-item
          v-if="editItemType === 'material'"
          :label="t('learning.items.descriptionField')"
        >
          <RichEditor
            v-model="editForm.description"
            :placeholder="t('learning.items.descriptionPlaceholder')"
          />
        </n-form-item>
        <n-form-item
          v-if="editItemType === 'material'"
          :label="t('learning.items.urlField')"
        >
          <n-input
            v-model:value="editForm.url"
            placeholder="https://"
            :maxlength="2048"
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
            :loading="editMut.isPending.value"
            @click="submitEdit"
          >
            {{ t('common.save') }}
          </n-button>
        </div>
      </template>
    </n-modal>

    <TestDrawer
      v-model:show="testOpen"
      :item-id="testItemId"
    />
  </section>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NAlert,
  NButton,
  NPopconfirm,
  NEmpty,
  NForm,
  NFormItem,
  NIcon,
  NInput,
  NModal,
  NRadio,
  NRadioGroup,
  NTag,
  useMessage,
} from 'naive-ui'
import { AddOutline, ChevronDownOutline, ChevronUpOutline, DocumentTextOutline, LinkOutline, PlayCircleOutline } from '@vicons/ionicons5'
import type { Component } from 'vue'
import {
  useAddItemMutation,
  useDeleteItemMutation,
  useReorderItemsMutation,
  useUpdateItemMutation,
  useUploadMaterialMutation,
} from '../../queries/learning'
import type { LearningItem } from '../../api/learning'
import { useMutationErrorToasts } from '../../composables/useMutationErrorToasts'
import { parseVideoEmbed } from '../../utils/videoEmbed'
import { useVideoOriginsQuery } from '../../queries/learning'
import RichEditor from '../RichEditor.vue'
import TestDrawer from './TestDrawer.vue'

const props = defineProps<{ courseId: string; items: LearningItem[] }>()
const { t } = useI18n()
const message = useMessage()

// Тот же гейт, что и на странице курса (/learning/meta, до загрузки — дефолт):
// бейдж «видео» показывается только там, где обучаемый получит плеер.
const { origins } = useVideoOriginsQuery()
function isVideo(item: LearningItem): boolean {
  if (item.type !== 'material' || !item.url) return false
  return parseVideoEmbed(item.url, origins.value) !== null
}

interface ItemFormatMeta {
  icon: Component
  label: string
  tooltip: string | null
}

/** Единый чип формата материала: PDF / Видео / Ссылка (ревью UI 2026-09-01).
 *  Тесты формата не имеют — их тип уже в теге слева. */
function formatMeta(item: LearningItem): ItemFormatMeta | null {
  if (item.type !== 'material') return null
  if (item.file_path) {
    return { icon: DocumentTextOutline, label: t('learning.items.formatPdf'), tooltip: null }
  }
  if (isVideo(item)) {
    return { icon: PlayCircleOutline, label: t('learning.items.formatVideo'), tooltip: item.url ?? null }
  }
  if (item.url) {
    return { icon: LinkOutline, label: t('learning.items.formatLink'), tooltip: item.url }
  }
  return null
}

const addMut = useAddItemMutation()
const editMut = useUpdateItemMutation()
const deleteMut = useDeleteItemMutation()
const reorderMut = useReorderItemsMutation()
const uploadMut = useUploadMaterialMutation()

useMutationErrorToasts(
  [addMut.error, editMut.error, deleteMut.error, reorderMut.error, uploadMut.error],
  (text) => message.error(text),
  t,
)

const orderedIds = () => props.items.map((i) => i.id)

async function move(idx: number, dir: -1 | 1) {
  const ids = orderedIds()
  const target = idx + dir
  if (target < 0 || target >= ids.length) return
  ;[ids[idx], ids[target]] = [ids[target], ids[idx]]
  try {
    await reorderMut.mutateAsync({ courseId: props.courseId, orderedIds: ids })
  } catch {
    // ошибка уже показана в watch
  }
}

const showAdd = ref(false)
const addForm = ref<{ type: 'material' | 'test' | 'section'; title: string; url: string; description: string }>({
  type: 'material',
  title: '',
  url: '',
  description: '',
})

async function submitAdd() {
  if (!addForm.value.title.trim()) {
    message.error(t('learning.items.titleRequired'))
    return
  }
  // URL при создании необязателен: PDF прикладывается к созданному элементу
  // отдельной кнопкой «Приложить PDF» (§6.2 ТЗ learning.md). Описание —
  // только материалу.
  const isMaterial = addForm.value.type === 'material'
  try {
    await addMut.mutateAsync({
      courseId: props.courseId,
      body: {
        type: addForm.value.type,
        title: addForm.value.title.trim(),
        url: isMaterial ? addForm.value.url.trim() || null : null,
        description: isMaterial ? addForm.value.description.trim() || null : null,
      },
    })
    showAdd.value = false
    addForm.value = { type: 'material', title: '', url: '', description: '' }
  } catch {
    // ошибка уже показана в watch
  }
}

const showEdit = ref(false)
const editItemId = ref<string | null>(null)
const editItemType = ref<'material' | 'test'>('material')
const editForm = ref<{ title: string; url: string; description: string }>({
  title: '',
  url: '',
  description: '',
})

function startEdit(item: LearningItem) {
  editItemId.value = item.id
  editItemType.value = item.type === 'test' ? 'test' : 'material'
  editForm.value = { title: item.title, url: item.url ?? '', description: item.description ?? '' }
  showEdit.value = true
}

async function submitEdit() {
  if (!editItemId.value || !editForm.value.title.trim()) return
  // Описание/url шлём только материалу (у теста их нет — бэкенд вернёт 422
  // на чужие поля), отсутствующий ключ = «не менять».
  const isMaterial = editItemType.value === 'material'
  try {
    await editMut.mutateAsync({
      courseId: props.courseId,
      itemId: editItemId.value,
      body: isMaterial
        ? {
            title: editForm.value.title.trim(),
            url: editForm.value.url.trim() || null,
            description: editForm.value.description.trim() || null,
          }
        : { title: editForm.value.title.trim() },
    })
    showEdit.value = false
  } catch {
    // ошибка уже показана в watch
  }
}

async function removeItem(itemId: string) {
  try {
    await deleteMut.mutateAsync({ courseId: props.courseId, itemId })
  } catch {
    // ошибка уже показана в watch
  }
}

const fileInput = ref<HTMLInputElement | null>(null)
let uploadItemId: string | null = null

function pickFile(itemId: string) {
  uploadItemId = itemId
  fileInput.value?.click()
}

async function onFilePicked(ev: Event) {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file || !uploadItemId) return
  try {
    await uploadMut.mutateAsync({ courseId: props.courseId, itemId: uploadItemId, file })
    message.success(t('learning.items.fileUploaded'))
  } catch {
    // ошибка уже показана в watch
  }
}

const testItemId = ref<string | null>(null)
const testOpen = ref(false)
watch(testItemId, (id) => {
  testOpen.value = id !== null
})
watch(testOpen, (open) => {
  if (!open) testItemId.value = null
})
</script>

<style scoped>
.panel-actions {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 12px;
}

.items-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.item-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 8px;
}

.item-row:hover {
  background: rgba(128, 128, 128, 0.08);
}

.item-order {
  display: flex;
  flex-direction: column;
}

.item-main {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.item-title {
  font-weight: 500;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* строка-заголовок раздела: читается как структура, а не как элемент */
.item-title--section {
  font-weight: 700;
  text-transform: none;
}

.item-row--section {
  border-top: 1px dashed var(--color-border, rgba(128, 128, 128, 0.35));
  border-radius: 0;
  padding-top: 10px;
}

/* колонка формата фиксированной ширины — чипы PDF/Видео/Ссылка стоят
   строго друг под другом; пустой слот у тестов держит сетку */
.item-format-slot {
  display: flex;
  justify-content: flex-start;
  flex-shrink: 0;
  width: 84px;
}

.item-format {
  color: var(--text-secondary, #999);
}

.item-actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}

/* Первая кнопка («Настроить тест» / «Заменить PDF» / «Приложить PDF») —
   одной ширины во всех строках: колонки действий стоят ровно друг под
   другом (ревью UI 2026-09-01). 112px хватает самому длинному тексту,
   контент n-button центрируется. */
.item-actions > :deep(.n-button:first-child) {
  width: 112px;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
