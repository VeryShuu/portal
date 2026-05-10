<template>
  <div>
    <div class="tab-toolbar">
      <n-button @click="loadAllDebounced" :loading="loading">
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


  </div>
</template>

<script setup lang="ts">
import { ref, h, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NDataTable, NButton, NInput, NInputNumber, NIcon, NModal, NForm, NFormItem,
  NSwitch, NTag, useMessage, type DataTableColumns,
} from 'naive-ui'
import { useConfirmDialog } from '../../../composables/useConfirmDialog'
import { AddOutline, CreateOutline, TrashOutline, RefreshOutline } from '@vicons/ionicons5'
import {
  createAttributeMapping,
  updateAttributeMapping,
  deleteAttributeMapping,
  type UserAttributeMapping,
  type DiscoverAttributeItem,
  type CreateUserAttributeMappingDto,
} from '../../../api/userAttributeMappings'
import { useUserAttributeMappingsQuery, useDiscoverAttributesQuery } from '../../../queries/admin'
import { useQueryClient } from '@tanstack/vue-query'
import { queryKeys } from '../../../queries/keys'

const { t } = useI18n()
const message = useMessage()
const { confirm } = useConfirmDialog()
const qc = useQueryClient()

const { data: mappingsData, isLoading: loading } = useUserAttributeMappingsQuery()
const { data: discoveredData } = useDiscoverAttributesQuery()

function loadAllDebounced() {
  qc.invalidateQueries({ queryKey: queryKeys.admin.userAttributes() })
  qc.invalidateQueries({ queryKey: queryKeys.admin.discoverAttributes() })
}

const mappings = computed(() => mappingsData.value?.items ?? [])
const discovered = computed(() => discoveredData.value?.items ?? [])

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

async function openDelete(m: UserAttributeMapping) {
  const ok = await confirm({
    title: t('admin.userAttributes.confirmDelete', { key: m.attr_key }),
    content: t('admin.userAttributes.confirmDeleteHint'),
    positiveText: t('common.delete'),
    negativeText: t('common.cancel'),
  })
  if (!ok) return
  try {
    await deleteAttributeMapping(m.id)
    qc.invalidateQueries({ queryKey: queryKeys.admin.userAttributes() })
    message.success(t('admin.userAttributes.deleted'))
  } catch {
    message.error(t('errors.generic'))
  }
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
      await updateAttributeMapping(editing.value.id, {
        label_ru: form.value.label_ru,
        label_en: form.value.label_en,
        sort_order: form.value.sort_order,
        enabled: form.value.enabled,
      })
    } else {
      await createAttributeMapping({
        attr_key: form.value.attr_key,
        label_ru: form.value.label_ru,
        label_en: form.value.label_en,
        sort_order: form.value.sort_order,
        enabled: form.value.enabled,
      })
    }
    qc.invalidateQueries({ queryKey: queryKeys.admin.userAttributes() })
    qc.invalidateQueries({ queryKey: queryKeys.admin.discoverAttributes() })
    message.success(t('admin.userAttributes.saved'))
    modalOpen.value = false
  } catch (e: any) {
    if ((e?.status ?? e?.response?.status) === 409) {
      message.error(t('admin.userAttributes.conflict'))
    } else {
      message.error(t('errors.generic'))
    }
  } finally {
    saving.value = false
  }
}


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
