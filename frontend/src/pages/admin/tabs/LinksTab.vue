<template>
  <div>
    <div class="tab-toolbar">
      <n-input
        v-model:value="linkSearch"
        :placeholder="t('common.search')"
        clearable
        style="max-width:260px"
      >
        <template #prefix>
          <n-icon><SearchOutline /></n-icon>
        </template>
      </n-input>
      <n-button
        type="primary"
        @click="openAddLink"
      >
        <template #icon>
          <n-icon><AddOutline /></n-icon>
        </template>
        {{ t('admin.links.add') }}
      </n-button>
    </div>

    <n-data-table
      :columns="linkColumns"
      :data="filteredLinks"
      :loading="loadingLinks"
      :pagination="{ pageSize: 20 }"
      :row-key="(row: ServiceLink) => row.id"
      striped
      class="data-table"
    />

    <n-modal
      v-model:show="linkModalOpen"
      :title="editingLink ? t('admin.links.editTitle') : t('admin.links.addTitle')"
      preset="card"
      style="width:540px;max-width:94vw"
      :mask-closable="false"
    >
      <n-form
        ref="linkFormRef"
        :model="linkForm"
        :rules="linkRules"
        label-placement="top"
      >
        <div class="form-row">
          <n-form-item
            :label="t('admin.links.form.titleLabel')"
            path="title"
          >
            <n-input
              v-model:value="linkForm.title"
              :placeholder="t('admin.links.form.titlePlaceholder')"
            />
          </n-form-item>
          <n-form-item
            :label="t('admin.links.form.urlLabel')"
            path="url"
          >
            <n-input
              v-model:value="linkForm.url"
              :placeholder="t('admin.links.form.urlPlaceholder')"
            />
          </n-form-item>
        </div>
        <div class="url-hint">
          {{ t('admin.links.form.urlHint') }}
        </div>
        <div class="form-row">
          <n-form-item :label="t('admin.links.form.categoryLabel')">
            <n-input
              v-model:value="linkForm.category"
              :placeholder="t('admin.links.form.categoryPlaceholder')"
              clearable
            />
          </n-form-item>
          <n-form-item :label="t('admin.links.form.sortOrderLabel')">
            <n-input-number
              v-model:value="linkForm.sort_order"
              :min="0"
              style="width:100%"
            />
          </n-form-item>
        </div>
        <n-form-item :label="t('admin.links.form.descriptionLabel')">
          <n-input
            v-model:value="linkForm.description"
            type="textarea"
            :rows="2"
            :placeholder="t('admin.links.form.descriptionPlaceholder')"
            clearable
          />
        </n-form-item>
        <n-form-item
          :label="t('admin.links.form.kbUrlLabel')"
          path="kb_url"
        >
          <n-input
            v-model:value="linkForm.kb_url"
            :placeholder="t('admin.links.form.kbUrlPlaceholder')"
            clearable
          />
        </n-form-item>
        <n-form-item :label="t('admin.links.form.iconLabel')">
          <div class="icon-upload-row">
            <div
              v-if="iconPreview || (editingLink && editingLink.icon_url)"
              class="icon-preview-wrap"
            >
              <img
                :src="iconPreview || editingLink!.icon_url!"
                class="icon-preview"
                alt=""
              >
              <n-button
                size="tiny"
                circle
                quaternary
                type="error"
                class="icon-preview-remove"
                @click="removeIcon"
              >
                ×
              </n-button>
            </div>
            <n-upload
              accept="image/png,image/jpeg,image/webp,image/svg+xml,image/x-icon"
              :max="1"
              :show-file-list="false"
              @change="onIconFileChange"
            >
              <n-button size="small">
                {{ t('admin.links.form.iconUploadBtn') }}
              </n-button>
            </n-upload>
          </div>
        </n-form-item>
        <div class="form-checks">
          <n-checkbox v-model:checked="linkForm.supports_sso">
            {{ t('admin.links.form.supportsSSO') }}
          </n-checkbox>
          <n-checkbox v-model:checked="linkForm.is_active">
            {{ t('admin.links.form.isActive') }}
          </n-checkbox>
          <n-checkbox v-model:checked="linkForm.show_on_home">
            {{ t('admin.links.form.showOnHome') }}
          </n-checkbox>
        </div>
      </n-form>
      <template #footer>
        <div class="modal-footer">
          <n-button @click="linkModalOpen = false">
            {{ t('common.cancel') }}
          </n-button>
          <n-button
            type="primary"
            :loading="savingLink"
            @click="submitLink"
          >
            {{ t('common.save') }}
          </n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onUnmounted, h } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NDataTable, NButton, NInput, NInputNumber, NIcon, NModal, NForm, NFormItem,
  NCheckbox, NTag, NUpload, useMessage, type DataTableColumns, type UploadFileInfo,
} from 'naive-ui'
import { useConfirmDialog } from '../../../composables/useConfirmDialog'
import { SearchOutline, AddOutline, CreateOutline, TrashOutline, ShieldCheckmarkOutline, HomeOutline } from '@vicons/ionicons5'
import { createLink, updateLink, deleteLink, uploadLinkIcon, deleteLinkIcon, type ServiceLink, type CreateLinkDto } from '../../../api/links'
import { isServiceLinkUrl } from '../../../utils/url'
import { useAdminLinksQuery } from '../../../queries/admin'
import { useQueryClient } from '@tanstack/vue-query'
import { queryKeys } from '../../../queries/keys'
import { useLinksStore } from '../../../stores/links'

const { t } = useI18n()
const message = useMessage()
const { confirm } = useConfirmDialog()
const qc = useQueryClient()
const store = useLinksStore()

const linkSearch = ref('')

const { data: linksData, isLoading: loadingLinks } = useAdminLinksQuery()
const links = computed(() => linksData.value?.items ?? [])

const filteredLinks = computed(() => {
  const q = linkSearch.value.trim().toLowerCase()
  if (!q) return links.value
  return links.value.filter(l =>
    l.title.toLowerCase().includes(q) ||
    l.url.toLowerCase().includes(q) ||
    (l.category ?? '').toLowerCase().includes(q),
  )
})

const linkModalOpen = ref(false)
const savingLink = ref(false)
const editingLink = ref<ServiceLink | null>(null)
const linkFormRef = ref()

const iconFile = ref<File | null>(null)
const iconPreview = ref<string | null>(null)
const iconRemoved = ref(false)

function onIconFileChange({ file }: { file: UploadFileInfo }) {
  if (file.file) {
    if (iconPreview.value) URL.revokeObjectURL(iconPreview.value)
    iconFile.value = file.file
    iconPreview.value = URL.createObjectURL(file.file)
    iconRemoved.value = false
  }
}

function removeIcon() {
  if (iconPreview.value) URL.revokeObjectURL(iconPreview.value)
  iconFile.value = null
  iconPreview.value = null
  iconRemoved.value = true
}

function resetIconState() {
  if (iconPreview.value) URL.revokeObjectURL(iconPreview.value)
  iconFile.value = null
  iconPreview.value = null
  iconRemoved.value = false
}

const emptyLinkForm = (): CreateLinkDto & { id?: string } => ({
  title: '',
  url: '',
  description: null,
  category: null,
  sort_order: 0,
  supports_sso: false,
  is_active: true,
  show_on_home: false,
  kb_url: null,
})

const linkForm = ref(emptyLinkForm())

const linkRules = computed(() => ({
  title: [{ required: true, message: t('admin.links.form.required'), trigger: 'blur' }],
  url: [
    { required: true, message: t('admin.links.form.required'), trigger: 'blur' },
    {
      validator: (_: unknown, value: string) => isServiceLinkUrl(value),
      message: t('admin.links.form.invalidUrl'),
      trigger: 'blur',
    },
  ],
  kb_url: [
    {
      validator: (_: unknown, value: string) => !value || isServiceLinkUrl(value),
      message: t('admin.links.form.invalidUrl'),
      trigger: 'blur',
    },
  ],
}))

const linkColumns = computed<DataTableColumns<ServiceLink>>(() => [
  {
    title: '',
    key: 'icon',
    width: 44,
    align: 'center',
    render: (row) =>
      row.icon_url
        ? h('img', { src: row.icon_url, style: 'width:24px;height:24px;object-fit:contain;vertical-align:middle', alt: '' })
        : null,
  },
  {
    title: t('admin.links.columns.title'),
    key: 'title',
    sorter: 'default',
    ellipsis: { tooltip: true },
  },
  {
    title: t('admin.links.columns.url'),
    key: 'url',
    ellipsis: { tooltip: true },
    render: (row) => h('span', { style: 'font-size:12px;color:var(--color-text-muted)' }, row.url),
  },
  {
    title: t('admin.links.columns.category'),
    key: 'category',
    width: 130,
    render: (row) => row.category ?? '—',
  },
  {
    title: t('admin.links.columns.sso'),
    key: 'supports_sso',
    width: 70,
    align: 'center',
    render: (row) =>
      row.supports_sso
        ? h(NIcon, { color: 'var(--color-brand-sky)', size: 18 }, { default: () => h(ShieldCheckmarkOutline) })
        : h('span', { style: 'color:var(--color-text-subtle)' }, '—'),
  },
  {
    title: t('admin.links.columns.active'),
    key: 'is_active',
    width: 90,
    align: 'center',
    render: (row) =>
      h(NTag, { size: 'small', type: row.is_active ? 'success' : 'default', bordered: false },
        { default: () => row.is_active ? t('common.yes') : t('common.no') }),
  },
  {
    title: t('admin.links.columns.showOnHome'),
    key: 'show_on_home',
    width: 90,
    align: 'center',
    render: (row) =>
      row.show_on_home
        ? h(NIcon, { color: 'var(--color-brand-sky)', size: 18 }, { default: () => h(HomeOutline) })
        : h('span', { style: 'color:var(--color-text-subtle)' }, '—'),
  },
  {
    title: t('admin.links.columns.actions'),
    key: 'actions',
    width: 100,
    align: 'center',
    render: (row) =>
      h('div', { style: 'display:flex;gap:6px;justify-content:center' }, [
        h(NButton, {
          size: 'small', quaternary: true, circle: true,
          title: t('common.edit'),
          onClick: () => openEditLink(row),
        }, { icon: () => h(NIcon, null, { default: () => h(CreateOutline) }) }),
        h(NButton, {
          size: 'small', quaternary: true, circle: true, type: 'error',
          title: t('common.delete'),
          onClick: () => openDeleteLink(row),
        }, { icon: () => h(NIcon, null, { default: () => h(TrashOutline) }) }),
      ]),
  },
])

function openAddLink() {
  editingLink.value = null
  linkForm.value = emptyLinkForm()
  resetIconState()
  linkModalOpen.value = true
}

function openEditLink(link: ServiceLink) {
  editingLink.value = link
  linkForm.value = {
    title: link.title,
    url: link.url,
    description: link.description,
    category: link.category,
    sort_order: link.sort_order,
    supports_sso: link.supports_sso,
    is_active: link.is_active,
    show_on_home: link.show_on_home,
    kb_url: link.kb_url,
  }
  resetIconState()
  linkModalOpen.value = true
}

async function openDeleteLink(link: ServiceLink) {
  const ok = await confirm({
    title: t('admin.links.confirmDelete', { title: link.title }),
    content: t('admin.links.confirmDeleteHint'),
    positiveText: t('common.delete'),
    negativeText: t('common.cancel'),
  })
  if (!ok) return
  try {
    await deleteLink(link.id)
    store.removeLink(link.id)
    qc.invalidateQueries({ queryKey: queryKeys.admin.links() })
    message.success(t('admin.links.deleted'))
  } catch {
    message.error(t('errors.generic'))
  }
}

async function submitLink() {
  try {
    await linkFormRef.value?.validate()
  } catch {
    return
  }
  savingLink.value = true
  try {
    const dto: CreateLinkDto = {
      title: linkForm.value.title,
      url: linkForm.value.url,
      description: linkForm.value.description || null,
      category: linkForm.value.category || null,
      sort_order: linkForm.value.sort_order ?? 0,
      supports_sso: linkForm.value.supports_sso,
      is_active: linkForm.value.is_active,
      show_on_home: linkForm.value.show_on_home,
      kb_url: linkForm.value.kb_url || null,
    }

    let saved: ServiceLink
    if (editingLink.value) {
      saved = await updateLink(editingLink.value.id, dto)
      store.updateLinkItem(saved)
    } else {
      saved = await createLink(dto)
      store.addLink(saved)
    }

    if (iconFile.value) {
      const withIcon = await uploadLinkIcon(saved.id, iconFile.value)
      store.updateLinkItem(withIcon)
    } else if (iconRemoved.value && editingLink.value?.icon_url) {
      await deleteLinkIcon(saved.id)
      store.clearLinkIcon(saved.id)
    }

    qc.invalidateQueries({ queryKey: queryKeys.admin.links() })
    message.success(t('admin.links.saved'))
    linkModalOpen.value = false
  } catch {
    message.error(t('errors.generic'))
  } finally {
    savingLink.value = false
  }
}

onUnmounted(() => {
  if (iconPreview.value) URL.revokeObjectURL(iconPreview.value)
})
</script>

<style scoped>
@import '../admin-tabs.css';

.url-hint {
  margin-top: -8px;
  margin-bottom: 8px;
  font-size: 12px;
  color: var(--color-text-muted);
}
</style>
