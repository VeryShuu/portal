<template>
  <div>
    <div class="tab-toolbar">
      <span class="categories-hint">{{ t('admin.newsCategories.hint') }}</span>
      <n-button
        type="primary"
        style="margin-left:auto"
        @click="openAdd"
      >
        <template #icon>
          <n-icon><AddOutline /></n-icon>
        </template>
        {{ t('admin.newsCategories.add') }}
      </n-button>
    </div>

    <n-data-table
      :columns="columns"
      :data="categories"
      :loading="loading"
      :pagination="{ pageSize: 50 }"
      :row-key="(row: NewsCategory) => row.name"
      striped
      class="data-table"
    />

    <n-modal
      v-model:show="renameModalOpen"
      :title="t('admin.newsCategories.renameTitle')"
      preset="card"
      style="width:400px;max-width:94vw"
      :mask-closable="false"
    >
      <n-form
        ref="renameFormRef"
        :model="renameForm"
        :rules="rules"
        label-placement="top"
      >
        <n-form-item
          :label="t('admin.newsCategories.nameLabel')"
          path="name"
        >
          <n-input
            v-model:value="renameForm.name"
            :placeholder="t('admin.newsCategories.namePlaceholder')"
            @keyup.enter="submitRename"
          />
        </n-form-item>
      </n-form>
      <template #footer>
        <div class="modal-footer">
          <n-button @click="renameModalOpen = false">
            {{ t('common.cancel') }}
          </n-button>
          <n-button
            type="primary"
            :loading="renaming"
            @click="submitRename"
          >
            {{ t('common.save') }}
          </n-button>
        </div>
      </template>
    </n-modal>

    <n-modal
      v-model:show="addModalOpen"
      :title="t('admin.newsCategories.addTitle')"
      preset="card"
      style="width:400px;max-width:94vw"
      :mask-closable="false"
    >
      <n-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-placement="top"
      >
        <n-form-item
          :label="t('admin.newsCategories.nameLabel')"
          path="name"
        >
          <n-input
            v-model:value="form.name"
            :placeholder="t('admin.newsCategories.namePlaceholder')"
            @keyup.enter="submit"
          />
        </n-form-item>
        <n-form-item :label="t('admin.newsCategories.colorLabel')">
          <div class="color-pick-row">
            <div
              class="color-swatch color-swatch--lg"
              :style="{ background: form.color }"
              role="button"
              tabindex="0"
              :aria-label="t('admin.newsCategories.colorLabel')"
              @click="addColorInputRef?.click()"
              @keydown.enter="addColorInputRef?.click()"
            />
            <input
              ref="addColorInputRef"
              type="color"
              :value="form.color"
              style="display:none"
              :aria-label="t('admin.newsCategories.colorLabel')"
              @input="(e) => form.color = (e.target as HTMLInputElement).value"
            >
            <span class="color-hex">{{ form.color.toUpperCase() }}</span>
          </div>
        </n-form-item>
      </n-form>
      <template #footer>
        <div class="modal-footer">
          <n-button @click="addModalOpen = false">
            {{ t('common.cancel') }}
          </n-button>
          <n-button
            type="primary"
            :loading="saving"
            @click="submit"
          >
            {{ t('common.save') }}
          </n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, h } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NDataTable, NButton, NIcon, NModal, NForm, NFormItem, NInput, NTag,
  useMessage, type DataTableColumns,
} from 'naive-ui'
import { useConfirmDialog } from '../../../composables/useConfirmDialog'
import { AddOutline, TrashOutline, CreateOutline } from '@vicons/ionicons5'
import {
  createNewsCategory,
  updateNewsCategoryColor,
  renameNewsCategory,
  deleteNewsCategory,
  type NewsCategory,
} from '../../../api/news'
import { useNewsCategoriesQuery } from '../../../queries/news'
import { useQueryClient } from '@tanstack/vue-query'
import { queryKeys } from '../../../queries/keys'

const { t } = useI18n()
const message = useMessage()
const { confirm } = useConfirmDialog()
const qc = useQueryClient()

const { data: categoriesData, isLoading: loading } = useNewsCategoriesQuery()
const categories = computed(() => categoriesData.value ?? [])

const addModalOpen = ref(false)
const saving = ref(false)
const formRef = ref()
const addColorInputRef = ref<HTMLInputElement | null>(null)

const renameModalOpen = ref(false)
const renaming = ref(false)
const renameFormRef = ref()
const renameForm = ref({ originalName: '', name: '' })

const DEFAULT_COLOR = '#6B7AE8'

const form = ref({ name: '', color: DEFAULT_COLOR })

const rules = computed(() => ({
  name: [{ required: true, message: t('admin.newsCategories.nameRequired'), trigger: 'blur' }],
}))



const columns = computed<DataTableColumns<NewsCategory>>(() => [
  {
    title: t('admin.newsCategories.columns.color'),
    key: 'color',
    width: 80,
    align: 'center',
    render: (row) => {
      const inputId = `color-input-${row.name}`
      return h('div', { style: 'display:flex;align-items:center;justify-content:center' }, [
        h('div', {
          style: {
            width: '28px',
            height: '28px',
            borderRadius: '4px',
            border: '1px solid var(--n-border-color, #e0e0e6)',
            background: row.color,
            cursor: 'pointer',
            flexShrink: '0',
            transition: 'transform 0.1s',
          },
          title: t('admin.newsCategories.changeColor'),
          onClick: () => {
            const el = document.getElementById(inputId) as HTMLInputElement | null
            el?.click()
          },
        }),
        h('input', {
          id: inputId,
          type: 'color',
          value: row.color,
          style: 'position:absolute;opacity:0;width:0;height:0;pointer-events:none',
          onChange: async (e: Event) => {
            const newColor = (e.target as HTMLInputElement).value
            await saveColor(row.name, newColor)
          },
        }),
      ])
    },
  },
  {
    title: t('admin.newsCategories.columns.name'),
    key: 'name',
    sorter: 'default',
    render: (row) =>
      h(NTag, {
        size: 'medium',
        bordered: false,
        style: { backgroundColor: row.color, color: contrastColor(row.color), fontWeight: '700' },
      }, { default: () => row.name }),
  },
  {
    title: t('admin.newsCategories.columns.newsCount'),
    key: 'news_count',
    width: 140,
    align: 'center',
    sorter: (a, b) => a.news_count - b.news_count,
    render: (row) => h('span', { style: 'color:var(--color-text-muted);font-size:13px' }, String(row.news_count)),
  },
  {
    title: t('admin.newsCategories.columns.actions'),
    key: 'actions',
    width: 120,
    align: 'center',
    render: (row) =>
      h('div', { style: 'display:flex;gap:4px;justify-content:center' }, [
        h(NButton, {
          size: 'small', quaternary: true, circle: true,
          title: t('admin.newsCategories.rename'),
          onClick: () => openRename(row.name),
        }, { icon: () => h(NIcon, null, { default: () => h(CreateOutline) }) }),
        h(NButton, {
          size: 'small', quaternary: true, circle: true, type: 'error',
          title: t('common.delete'),
          onClick: () => openDelete(row.name),
        }, { icon: () => h(NIcon, null, { default: () => h(TrashOutline) }) }),
      ]),
  },
])

function contrastColor(hex: string): string {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
  return luminance > 0.55 ? '#1a1a1a' : '#ffffff'
}

async function saveColor(name: string, color: string) {
  try {
    await updateNewsCategoryColor(name, color)
    qc.invalidateQueries({ queryKey: queryKeys.news.categories() })
  } catch {
    message.error(t('errors.generic'))
  }
}

function openAdd() {
  form.value = { name: '', color: DEFAULT_COLOR }
  addModalOpen.value = true
}

async function submit() {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  saving.value = true
  try {
    await createNewsCategory(form.value.name.trim(), form.value.color)
    qc.invalidateQueries({ queryKey: queryKeys.news.categories() })
    message.success(t('news.categories.added'))
    addModalOpen.value = false
  } catch (err: unknown) {
    const status = (err as { response?: { status?: number } })?.response?.status
    if (status === 409) {
      message.error(t('news.categories.exists'))
    } else {
      message.error(t('errors.generic'))
    }
  } finally {
    saving.value = false
  }
}

function openRename(name: string) {
  renameForm.value = { originalName: name, name }
  renameModalOpen.value = true
}

async function submitRename() {
  try {
    await renameFormRef.value?.validate()
  } catch {
    return
  }
  const newName = renameForm.value.name.trim()
  if (!newName || newName === renameForm.value.originalName) {
    renameModalOpen.value = false
    return
  }
  renaming.value = true
  try {
    await renameNewsCategory(renameForm.value.originalName, newName)
    qc.invalidateQueries({ queryKey: queryKeys.news.categories() })
    qc.invalidateQueries({ queryKey: queryKeys.news.all })
    message.success(t('news.categories.renamed'))
    renameModalOpen.value = false
  } catch (err: unknown) {
    const status = (err as { response?: { status?: number } })?.response?.status
    if (status === 409) {
      message.error(t('news.categories.exists'))
    } else {
      message.error(t('errors.generic'))
    }
  } finally {
    renaming.value = false
  }
}

async function openDelete(name: string) {
  const ok = await confirm({
    title: t('admin.newsCategories.confirmDelete', { name }),
    content: t('admin.newsCategories.confirmDeleteHint'),
    positiveText: t('common.delete'),
    negativeText: t('common.cancel'),
  })
  if (!ok) return
  try {
    await deleteNewsCategory(name)
    qc.invalidateQueries({ queryKey: queryKeys.news.categories() })
    message.success(t('news.categories.deleted'))
  } catch {
    message.error(t('errors.generic'))
  }
}


</script>

<style scoped>
@import '../admin-tabs.css';

.categories-hint {
  font-size: 13px;
  color: var(--color-text-muted);
}

.color-swatch {
  width: 28px;
  height: 28px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border);
  flex-shrink: 0;
  transition: transform 0.1s;
}
.color-swatch:hover {
  transform: scale(1.1);
}
.color-swatch--lg {
  width: 36px;
  height: 36px;
  cursor: pointer;
}

.color-pick-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.color-hex {
  font-family: var(--font-mono, monospace);
  font-size: 13px;
  color: var(--color-text-muted);
}
</style>
