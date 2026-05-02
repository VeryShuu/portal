<template>
  <div>
    <div class="tab-toolbar">
      <n-button @click="loadAll" :loading="loading">
        <template #icon><n-icon><RefreshOutline /></n-icon></template>
        {{ t('common.refresh') }}
      </n-button>
      <n-button type="primary" @click="openAdd">
        <template #icon><n-icon><AddOutline /></n-icon></template>
        {{ t('admin.userAttributes.add') }}
      </n-button>
    </div>

    <n-data-table
      :columns="columns"
      :data="mappings"
      :loading="loading"
      :pagination="{ pageSize: 20 }"
      :row-key="(row: UserAttributeMapping) => row.id"
      striped
      class="data-table"
    />

    <section v-if="discovered.length" class="discover-section">
      <h3 class="discover-title">{{ t('admin.userAttributes.discoverTitle') }}</h3>
      <p class="discover-hint">{{ t('admin.userAttributes.discoverHint') }}</p>
      <n-data-table
        :columns="discoverColumns"
        :data="discovered"
        :pagination="{ pageSize: 10 }"
        :row-key="(row: DiscoverAttributeItem) => row.attr_key"
        striped
        class="data-table"
      />
    </section>

    <n-modal
      v-model:show="modalOpen"
      :title="editing ? t('admin.userAttributes.editTitle') : t('admin.userAttributes.addTitle')"
      preset="card"
      style="width:520px;max-width:94vw"
      :mask-closable="false"
    >
      <n-form :model="form" :rules="rules" ref="formRef" label-placement="top">
        <n-form-item :label="t('admin.userAttributes.form.attrKey')" path="attr_key">
          <n-input
            v-model:value="form.attr_key"
            :disabled="!!editing"
            placeholder="city"
          />
        </n-form-item>
        <n-form-item :label="t('admin.userAttributes.form.labelRu')" path="label_ru">
          <n-input v-model:value="form.label_ru" />
        </n-form-item>
        <n-form-item :label="t('admin.userAttributes.form.labelEn')">
          <n-input v-model:value="form.label_en" clearable />
        </n-form-item>
        <div class="form-row">
          <n-form-item :label="t('admin.userAttributes.form.sortOrder')">
            <n-input-number v-model:value="form.sort_order" :min="0" style="width:100%" />
          </n-form-item>
          <n-form-item :label="t('admin.userAttributes.form.enabled')">
            <n-switch v-model:value="form.enabled" />
          </n-form-item>
        </div>
      </n-form>
      <template #footer>
        <div class="modal-footer">
          <n-button @click="modalOpen = false">{{ t('common.cancel') }}</n-button>
          <n-button type="primary" :loading="saving" @click="submit">{{ t('common.save') }}</n-button>
        </div>
      </template>
    </n-modal>

    <n-modal
      v-model:show="deleteOpen"
      :title="t('admin.userAttributes.confirmDelete', { key: deleting?.attr_key ?? '' })"
      preset="dialog"
      type="warning"
      :positive-text="t('common.delete')"
      :negative-text="t('common.cancel')"
      @positive-click="confirmDelete"
    >
      {{ t('admin.userAttributes.confirmDeleteHint') }}
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, h, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NDataTable, NButton, NInput, NInputNumber, NIcon, NModal, NForm, NFormItem,
  NSwitch, NTag, useMessage, type DataTableColumns,
} from 'naive-ui'
import { AddOutline, CreateOutline, TrashOutline, RefreshOutline } from '@vicons/ionicons5'
import {
  fetchAttributeMappings,
  createAttributeMapping,
  updateAttributeMapping,
  deleteAttributeMapping,
  discoverAttributes,
  type UserAttributeMapping,
  type DiscoverAttributeItem,
  type CreateUserAttributeMappingDto,
} from '../../../api/userAttributeMappings'

const { t } = useI18n()
const message = useMessage()

const mappings = ref<UserAttributeMapping[]>([])
const discovered = ref<DiscoverAttributeItem[]>([])
const loading = ref(false)

const modalOpen = ref(false)
const saving = ref(false)
const editing = ref<UserAttributeMapping | null>(null)
const formRef = ref()

const emptyForm = (): CreateUserAttributeMappingDto & { id?: string } => ({
  attr_key: '',
  label_ru: '',
  label_en: null,
  sort_order: 0,
  enabled: true,
})

const form = ref(emptyForm())

const rules = computed(() => ({
  attr_key: [{ required: true, message: t('admin.userAttributes.form.required'), trigger: 'blur' }],
  label_ru: [{ required: true, message: t('admin.userAttributes.form.required'), trigger: 'blur' }],
}))

const deleteOpen = ref(false)
const deleting = ref<UserAttributeMapping | null>(null)

const columns = computed<DataTableColumns<UserAttributeMapping>>(() => [
  { title: t('admin.userAttributes.columns.attrKey'), key: 'attr_key', width: 200, sorter: 'default' },
  { title: t('admin.userAttributes.columns.labelRu'), key: 'label_ru', sorter: 'default' },
  { title: t('admin.userAttributes.columns.labelEn'), key: 'label_en', render: r => r.label_en ?? '—' },
  { title: t('admin.userAttributes.columns.sortOrder'), key: 'sort_order', width: 100, align: 'center' },
  {
    title: t('admin.userAttributes.columns.enabled'),
    key: 'enabled',
    width: 100,
    align: 'center',
    render: (row) =>
      h(NTag, { size: 'small', type: row.enabled ? 'success' : 'default', bordered: false },
        { default: () => row.enabled ? t('common.yes') : t('common.no') }),
  },
  {
    title: t('admin.userAttributes.columns.actions'),
    key: 'actions',
    width: 100,
    align: 'center',
    render: (row) =>
      h('div', { style: 'display:flex;gap:6px;justify-content:center' }, [
        h(NButton, {
          size: 'small', quaternary: true, circle: true,
          title: t('common.edit'),
          onClick: () => openEdit(row),
        }, { icon: () => h(NIcon, null, { default: () => h(CreateOutline) }) }),
        h(NButton, {
          size: 'small', quaternary: true, circle: true, type: 'error',
          title: t('common.delete'),
          onClick: () => openDelete(row),
        }, { icon: () => h(NIcon, null, { default: () => h(TrashOutline) }) }),
      ]),
  },
])

const discoverColumns = computed<DataTableColumns<DiscoverAttributeItem>>(() => [
  { title: t('admin.userAttributes.columns.attrKey'), key: 'attr_key', width: 220 },
  { title: t('admin.userAttributes.discover.sample'), key: 'sample', render: r => r.sample ?? '—' },
  { title: t('admin.userAttributes.discover.occurrences'), key: 'occurrences', width: 120, align: 'center' },
  {
    title: t('admin.userAttributes.columns.actions'),
    key: 'actions',
    width: 140,
    align: 'center',
    render: (row) =>
      h(NButton, {
        size: 'small', type: 'primary',
        onClick: () => openAddFromDiscover(row),
      }, { default: () => t('admin.userAttributes.add') }),
  },
])

async function loadAll() {
  loading.value = true
  try {
    const [list, disc] = await Promise.all([fetchAttributeMappings(), discoverAttributes()])
    mappings.value = list.items
    discovered.value = disc.items
  } catch {
    message.error(t('errors.generic'))
  } finally {
    loading.value = false
  }
}

function openAdd() {
  editing.value = null
  form.value = emptyForm()
  modalOpen.value = true
}

function openAddFromDiscover(item: DiscoverAttributeItem) {
  editing.value = null
  form.value = { ...emptyForm(), attr_key: item.attr_key, label_ru: item.attr_key }
  modalOpen.value = true
}

function openEdit(m: UserAttributeMapping) {
  editing.value = m
  form.value = {
    attr_key: m.attr_key,
    label_ru: m.label_ru,
    label_en: m.label_en,
    sort_order: m.sort_order,
    enabled: m.enabled,
  }
  modalOpen.value = true
}

function openDelete(m: UserAttributeMapping) {
  deleting.value = m
  deleteOpen.value = true
}

async function submit() {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  saving.value = true
  try {
    if (editing.value) {
      const saved = await updateAttributeMapping(editing.value.id, {
        label_ru: form.value.label_ru,
        label_en: form.value.label_en,
        sort_order: form.value.sort_order,
        enabled: form.value.enabled,
      })
      const idx = mappings.value.findIndex(x => x.id === editing.value!.id)
      if (idx !== -1) mappings.value[idx] = saved
    } else {
      const saved = await createAttributeMapping({
        attr_key: form.value.attr_key,
        label_ru: form.value.label_ru,
        label_en: form.value.label_en,
        sort_order: form.value.sort_order,
        enabled: form.value.enabled,
      })
      mappings.value.push(saved)
      discovered.value = discovered.value.filter(d => d.attr_key !== saved.attr_key)
    }
    message.success(t('admin.userAttributes.saved'))
    modalOpen.value = false
  } catch (e: any) {
    if (e?.response?.status === 409) {
      message.error(t('admin.userAttributes.conflict'))
    } else {
      message.error(t('errors.generic'))
    }
  } finally {
    saving.value = false
  }
}

async function confirmDelete() {
  if (!deleting.value) return
  try {
    await deleteAttributeMapping(deleting.value.id)
    mappings.value = mappings.value.filter(x => x.id !== deleting.value!.id)
    message.success(t('admin.userAttributes.deleted'))
  } catch {
    message.error(t('errors.generic'))
  } finally {
    deleting.value = null
  }
}

onMounted(() => {
  void loadAll()
})
</script>

<style scoped>
@import '../admin-tabs.css';

.discover-section {
  margin-top: 28px;
}
.discover-title {
  margin: 0 0 4px 0;
  font-size: 16px;
  font-weight: 700;
}
.discover-hint {
  margin: 0 0 12px 0;
  color: var(--color-text-muted);
  font-size: 13px;
}
.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.modal-footer {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}
</style>
