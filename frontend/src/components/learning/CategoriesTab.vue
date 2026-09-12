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
        {{ t('learning.categories.add') }}
      </n-button>
    </div>

    <n-empty
      v-if="categories.length === 0"
      :description="t('learning.categories.empty')"
    />
    <div
      v-else
      class="cat-list"
    >
      <div
        v-for="(cat, idx) in categories"
        :key="cat.id"
        class="cat-row"
      >
        <div class="cat-order">
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
            :disabled="idx === categories.length - 1 || reorderMut.isPending.value"
            @click="move(idx, 1)"
          >
            <n-icon><ChevronDownOutline /></n-icon>
          </n-button>
        </div>
        <span class="cat-title">{{ cat.title }}</span>
        <n-tag
          size="tiny"
          :bordered="false"
          class="cat-count"
        >
          {{ t('learning.categories.coursesCount', cat.course_count) }}
        </n-tag>
        <div class="cat-actions">
          <n-button
            size="tiny"
            @click="startRename(cat)"
          >
            {{ t('common.edit') }}
          </n-button>
          <n-popconfirm
            :show-icon="false"
            @positive-click="removeCat(cat.id)"
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
            {{ t('learning.categories.deleteConfirm') }}
          </n-popconfirm>
        </div>
      </div>
    </div>

    <n-modal
      v-model:show="showAdd"
      preset="card"
      :title="t('learning.categories.addTitle')"
      style="max-width: 420px"
    >
      <n-input
        v-model:value="newTitle"
        :maxlength="255"
        :placeholder="t('learning.categories.titleField')"
        @keyup.enter="submitAdd"
      />
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
      v-model:show="showRename"
      preset="card"
      :title="t('learning.categories.editTitle')"
      style="max-width: 420px"
    >
      <n-input
        v-model:value="renameTitle"
        :maxlength="255"
        :placeholder="t('learning.categories.titleField')"
        @keyup.enter="submitRename"
      />
      <template #footer>
        <div class="modal-actions">
          <n-button @click="showRename = false">
            {{ t('common.cancel') }}
          </n-button>
          <n-button
            type="primary"
            :loading="renameMut.isPending.value"
            @click="submitRename"
          >
            {{ t('common.save') }}
          </n-button>
        </div>
      </template>
    </n-modal>
  </section>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NButton,
  NEmpty,
  NIcon,
  NInput,
  NModal,
  NPopconfirm,
  NTag,
  useMessage,
} from 'naive-ui'
import { AddOutline, ChevronDownOutline, ChevronUpOutline } from '@vicons/ionicons5'
import {
  useCategoriesQuery,
  useCreateCategoryMutation,
  useDeleteCategoryMutation,
  useReorderCategoriesMutation,
  useUpdateCategoryMutation,
} from '../../queries/learning'
import type { LearningCategory } from '../../api/learning'
import { useMutationErrorToasts } from '../../composables/useMutationErrorToasts'

const { t } = useI18n()
const message = useMessage()

const query = useCategoriesQuery()
const categories = ref<LearningCategory[]>([])
// данные запроса → локальный список: reorder отвечает мгновенно и держит порядок
watch(
  () => query.data.value,
  (d) => {
    categories.value = d ?? []
  },
  { immediate: true },
)

const addMut = useCreateCategoryMutation()
const renameMut = useUpdateCategoryMutation()
const deleteMut = useDeleteCategoryMutation()
const reorderMut = useReorderCategoriesMutation()
useMutationErrorToasts(
  [addMut.error, renameMut.error, deleteMut.error, reorderMut.error],
  (text) => message.error(text),
  t,
)

async function move(idx: number, dir: -1 | 1) {
  const ids = categories.value.map((c) => c.id)
  const target = idx + dir
  if (target < 0 || target >= ids.length) return
  ;[ids[idx], ids[target]] = [ids[target], ids[idx]]
  try {
    await reorderMut.mutateAsync({ ordered_ids: ids })
  } catch {
    // ошибка уже показана в watch
  }
}

const showAdd = ref(false)
const newTitle = ref('')

async function submitAdd() {
  if (!newTitle.value.trim()) {
    message.error(t('learning.categories.titleRequired'))
    return
  }
  try {
    await addMut.mutateAsync({ title: newTitle.value.trim() })
    message.success(t('learning.categories.created'))
    showAdd.value = false
    newTitle.value = ''
  } catch {
    // ошибка уже показана в watch
  }
}

const showRename = ref(false)
const renameId = ref<string | null>(null)
const renameTitle = ref('')

function startRename(cat: LearningCategory) {
  renameId.value = cat.id
  renameTitle.value = cat.title
  showRename.value = true
}

async function submitRename() {
  if (!renameId.value || !renameTitle.value.trim()) {
    message.error(t('learning.categories.titleRequired'))
    return
  }
  try {
    await renameMut.mutateAsync({ id: renameId.value, body: { title: renameTitle.value.trim() } })
    message.success(t('learning.categories.renamed'))
    showRename.value = false
  } catch {
    // ошибка уже показана в watch
  }
}

async function removeCat(id: string) {
  try {
    await deleteMut.mutateAsync(id)
    message.success(t('learning.categories.deleted'))
  } catch {
    // ошибка уже показана в watch
  }
}
</script>

<style scoped>
.panel-actions {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 12px;
}

.cat-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.cat-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 8px;
}

.cat-row:hover {
  background: rgba(128, 128, 128, 0.08);
}

.cat-order {
  display: flex;
  flex-direction: column;
}

.cat-title {
  flex: 1;
  min-width: 0;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cat-count {
  color: var(--text-secondary, #999);
  flex-shrink: 0;
}

.cat-actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
