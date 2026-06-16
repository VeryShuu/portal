<template>
  <div>
    <div class="tab-toolbar">
      <span class="recipients-hint">{{ t('mailingRecipients.hint') }}</span>
      <n-button
        type="primary"
        style="margin-left:auto"
        @click="openAdd"
      >
        <template #icon>
          <n-icon><AddOutline /></n-icon>
        </template>
        {{ t('mailingRecipients.add') }}
      </n-button>
    </div>

    <n-input
      v-model:value="search"
      clearable
      :placeholder="t('mailingRecipients.searchPlaceholder')"
      style="margin-bottom:12px"
    >
      <template #prefix>
        <n-icon><SearchOutline /></n-icon>
      </template>
    </n-input>

    <n-data-table
      :columns="columns"
      :data="recipients"
      :loading="loading"
      :pagination="{ pageSize: 50 }"
      :row-key="(row: MailingRecipient) => row.id"
      striped
      class="data-table"
    />

    <n-modal
      v-model:show="modalOpen"
      :title="editing ? t('mailingRecipients.editTitle') : t('mailingRecipients.addTitle')"
      preset="card"
      style="width:440px;max-width:94vw"
      :mask-closable="false"
    >
      <n-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-placement="top"
      >
        <n-form-item
          :label="t('mailingRecipients.nameLabel')"
          path="name"
        >
          <n-input
            v-model:value="form.name"
            :placeholder="t('mailingRecipients.namePlaceholder')"
          />
        </n-form-item>
        <n-form-item
          :label="t('mailingRecipients.emailLabel')"
          path="email"
        >
          <n-input
            v-model:value="form.email"
            :placeholder="t('mailingRecipients.emailPlaceholder')"
          />
        </n-form-item>
        <n-form-item :label="t('mailingRecipients.labelLabel')">
          <n-input
            v-model:value="form.label"
            :placeholder="t('mailingRecipients.labelPlaceholder')"
          />
        </n-form-item>
      </n-form>
      <template #footer>
        <div class="modal-footer">
          <n-button @click="modalOpen = false">
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
  NDataTable, NButton, NIcon, NModal, NForm, NFormItem, NInput,
  useMessage, type DataTableColumns, type FormRules,
} from 'naive-ui'
import { useConfirmDialog } from '../../composables/useConfirmDialog'
import { AddOutline, TrashOutline, CreateOutline, SearchOutline } from '@vicons/ionicons5'
import { type MailingRecipient } from '../../api/mailingRecipients'
import {
  useMailingRecipientsQuery,
  useCreateMailingRecipientMutation,
  useUpdateMailingRecipientMutation,
  useDeleteMailingRecipientMutation,
} from '../../queries/mailingRecipients'

const { t } = useI18n()
const message = useMessage()
const { confirm } = useConfirmDialog()

const search = ref('')
const params = computed(() => ({ q: search.value || undefined, limit: 200 }))
const { data: recipientsData, isLoading: loading } = useMailingRecipientsQuery(params)
const recipients = computed(() => recipientsData.value?.items ?? [])

const createMutation = useCreateMailingRecipientMutation()
const updateMutation = useUpdateMailingRecipientMutation()
const deleteMutation = useDeleteMailingRecipientMutation()

const modalOpen = ref(false)
const saving = ref(false)
const formRef = ref()
const editing = ref<MailingRecipient | null>(null)
const form = ref({ name: '', email: '', label: '' })

const rules = computed<FormRules>(() => ({
  name: [{ required: true, message: t('mailingRecipients.nameRequired'), trigger: 'blur' }],
  email: [{ required: true, message: t('mailingRecipients.emailRequired'), trigger: 'blur' }],
}))

const columns = computed<DataTableColumns<MailingRecipient>>(() => [
  {
    title: t('mailingRecipients.columns.name'),
    key: 'name',
    sorter: 'default',
  },
  {
    title: t('mailingRecipients.columns.email'),
    key: 'email',
  },
  {
    title: t('mailingRecipients.columns.label'),
    key: 'label',
    render: (row) =>
      row.label
        ? row.label
        : h('span', { style: 'color:var(--color-text-muted)' }, '—'),
  },
  {
    title: t('mailingRecipients.columns.actions'),
    key: 'actions',
    width: 120,
    align: 'center',
    render: (row) =>
      h('div', { style: 'display:flex;gap:4px;justify-content:center' }, [
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

function openAdd() {
  editing.value = null
  form.value = { name: '', email: '', label: '' }
  modalOpen.value = true
}

function openEdit(row: MailingRecipient) {
  editing.value = row
  form.value = { name: row.name, email: row.email, label: row.label ?? '' }
  modalOpen.value = true
}

async function submit() {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  saving.value = true
  const payload = {
    name: form.value.name.trim(),
    email: form.value.email.trim(),
    label: form.value.label.trim() || null,
  }
  try {
    if (editing.value) {
      await updateMutation.mutateAsync({ id: editing.value.id, dto: payload })
      message.success(t('mailingRecipients.updated'))
    } else {
      await createMutation.mutateAsync(payload)
      message.success(t('mailingRecipients.added'))
    }
    modalOpen.value = false
  } catch (err: unknown) {
    const status = (err as { response?: { status?: number } })?.response?.status
    if (status === 409) {
      message.error(t('mailingRecipients.exists'))
    } else {
      message.error(t('errors.generic'))
    }
  } finally {
    saving.value = false
  }
}

async function openDelete(row: MailingRecipient) {
  const ok = await confirm({
    title: t('mailingRecipients.confirmDelete', { name: row.name }),
    content: t('mailingRecipients.confirmDeleteHint'),
    positiveText: t('common.delete'),
    negativeText: t('common.cancel'),
  })
  if (!ok) return
  try {
    await deleteMutation.mutateAsync(row.id)
    message.success(t('mailingRecipients.deleted'))
  } catch {
    message.error(t('errors.generic'))
  }
}
</script>

<style scoped>
@import '../../pages/admin/admin-tabs.css';

.recipients-hint {
  font-size: 13px;
  color: var(--color-text-muted);
}
</style>
