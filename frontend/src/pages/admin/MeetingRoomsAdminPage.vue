<template>
  <div class="admin-rooms">
    <div class="admin-rooms__header">
      <h2 class="admin-rooms__title">
        {{ t('meetings.admin.title') }}
      </h2>
      <n-button
        type="primary"
        size="small"
        @click="openCreateForm"
      >
        + {{ t('meetings.admin.addRoom') }}
      </n-button>
    </div>

    <div class="admin-rooms__filters">
      <n-switch
        v-model:value="onlyActive"
        size="small"
      />
      <span class="admin-rooms__filter-label">{{ t('meetings.admin.onlyActive') }}</span>
    </div>

    <n-data-table
      :columns="columns"
      :data="filteredRooms"
      :loading="isLoading"
      :row-key="(r: MeetingRoom) => r.id"
      :pagination="pagination"
      size="small"
    />

    <n-modal
      v-model:show="formVisible"
      :title="isEdit ? t('meetings.admin.editRoom') : t('meetings.admin.addRoom')"
      preset="card"
      style="max-width: 440px"
      :mask-closable="false"
    >
      <n-form
        ref="formRef"
        :model="form"
        label-placement="top"
      >
        <n-form-item
          :label="t('meetings.admin.roomName')"
          path="name"
          :rule="{ required: true, message: t('meetings.admin.roomNameRequired') }"
        >
          <n-input
            v-model:value="form.name"
            :placeholder="t('meetings.admin.roomNamePlaceholder')"
            maxlength="200"
          />
        </n-form-item>

        <n-form-item
          :label="t('meetings.admin.roomKind')"
          path="kind"
        >
          <n-radio-group v-model:value="form.kind">
            <n-radio value="physical">
              {{ t('meetings.admin.roomKindPhysical') }}
            </n-radio>
            <n-radio value="virtual">
              {{ t('meetings.admin.roomKindVirtual') }}
            </n-radio>
          </n-radio-group>
        </n-form-item>

        <n-form-item
          :label="t('meetings.admin.roomEmail')"
          path="email"
          :rule="{ type: 'email', message: t('meetings.admin.roomEmailInvalid'), trigger: 'blur' }"
        >
          <n-input
            v-model:value="form.email"
            :placeholder="t('meetings.admin.roomEmailPlaceholder')"
            clearable
          />
        </n-form-item>

        <n-form-item
          :label="t('meetings.admin.roomLink')"
          path="link"
          :rule="{
            trigger: ['blur', 'input'],
            validator: (_rule: unknown, value: string) => {
              if (!value) return true
              return isServiceLinkUrl(value)
                ? true
                : new Error(t('meetings.admin.roomLinkInvalidScheme'))
            },
          }"
        >
          <n-input
            v-model:value="form.link"
            :placeholder="t('meetings.admin.roomLinkPlaceholder')"
            clearable
          />
        </n-form-item>

        <n-form-item
          :label="t('meetings.admin.roomTimezone')"
          path="timezone"
        >
          <n-select
            v-model:value="form.timezone"
            filterable
            :options="timezoneOptions"
            :placeholder="t('meetings.admin.roomTimezonePlaceholder')"
          />
        </n-form-item>

        <n-form-item :label="t('meetings.admin.roomSortOrder')">
          <n-input-number
            v-model:value="form.sort_order"
            :min="0"
            :max="9999"
          />
        </n-form-item>

        <n-form-item
          v-if="isEdit"
          :label="t('meetings.admin.roomActive')"
        >
          <n-switch v-model:value="form.is_active" />
        </n-form-item>
      </n-form>

      <template #footer>
        <n-space justify="end">
          <n-button @click="formVisible = false">
            {{ t('common.cancel') }}
          </n-button>
          <n-button
            type="primary"
            :loading="saving"
            @click="onSave"
          >
            {{ t('common.save') }}
          </n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, h } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NButton, NDataTable, NModal, NForm, NFormItem, NInput, NSelect,
  NInputNumber, NSwitch, NSpace, NTag, NRadio, NRadioGroup,
  useMessage,
  type DataTableColumns, type FormInst,
} from 'naive-ui'
import { useMeetingRoomsQuery, useCreateRoomMutation, useUpdateRoomMutation, useDeleteRoomMutation } from '../../queries/meetings'
import { useSystemSettingsQuery } from '../../queries/admin'
import type { MeetingRoom, RoomKind } from '../../api/meetings'
import { parseApiError } from '../../utils/parseApiError'
import { isServiceLinkUrl } from '../../utils/url'

const { t } = useI18n()
const message = useMessage()

const { data: roomsData, isLoading } = useMeetingRoomsQuery(true)
const rooms = computed(() => roomsData.value ?? [])
const { data: systemSettings } = useSystemSettingsQuery()
const portalTimezone = computed(() => systemSettings.value?.timezone ?? 'Europe/Moscow')

const onlyActive = ref(false)
const filteredRooms = computed(() =>
  onlyActive.value ? rooms.value.filter(r => r.is_active) : rooms.value,
)
const pagination = { pageSize: 20 }

const { mutateAsync: doCreate } = useCreateRoomMutation()
const { mutateAsync: doUpdate } = useUpdateRoomMutation()
const { mutateAsync: doDelete } = useDeleteRoomMutation()

const formRef = ref<FormInst | null>(null)
const formVisible = ref(false)
const isEdit = ref(false)
const editId = ref<string | null>(null)
const saving = ref(false)

const form = ref({
  name: '',
  kind: 'physical' as RoomKind,
  email: '',
  link: '',
  timezone: 'Europe/Moscow',
  sort_order: 0,
  is_active: true,
})

const fallbackTimezones = [
  'Europe/Moscow', 'Europe/Kaliningrad', 'Europe/Samara', 'Asia/Yekaterinburg',
  'Asia/Omsk', 'Asia/Krasnoyarsk', 'Asia/Irkutsk', 'Asia/Yakutsk',
  'Asia/Vladivostok', 'Asia/Magadan', 'Asia/Kamchatka',
  'Europe/London', 'Europe/Berlin', 'Europe/Paris', 'America/New_York', 'America/Los_Angeles',
  'UTC',
]

const timezoneOptions = computed(() => {
  const intl = (Intl as unknown as { supportedValuesOf?: (k: string) => string[] }).supportedValuesOf
  const list = typeof intl === 'function' ? intl('timeZone') : fallbackTimezones
  return list.map(tz => ({ label: tz, value: tz }))
})

function openCreateForm() {
  isEdit.value = false
  editId.value = null
  form.value = { name: '', kind: 'physical', email: '', link: '', timezone: portalTimezone.value, sort_order: 0, is_active: true }
  formVisible.value = true
}

function openEditForm(room: MeetingRoom) {
  isEdit.value = true
  editId.value = room.id
  form.value = {
    name: room.name,
    kind: room.kind,
    email: room.email ?? '',
    link: room.link ?? '',
    timezone: room.timezone,
    sort_order: room.sort_order,
    is_active: room.is_active,
  }
  formVisible.value = true
}

async function onSave() {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  saving.value = true
  try {
    const dto = {
      name: form.value.name,
      kind: form.value.kind,
      email: form.value.email || null,
      link: form.value.link || null,
      timezone: form.value.timezone,
      sort_order: form.value.sort_order,
    }
    if (isEdit.value && editId.value) {
      await doUpdate({ id: editId.value, dto: { ...dto, is_active: form.value.is_active } })
    } else {
      await doCreate(dto)
    }
    message.success(t('meetings.admin.savedSuccess'))
    formVisible.value = false
  } catch {
    message.error(t('meetings.admin.saveError'))
  } finally {
    saving.value = false
  }
}

async function onDelete(room: MeetingRoom) {
  try {
    await doDelete(room.id)
    message.success(t('meetings.admin.deletedSuccess'))
  } catch (err: unknown) {
    message.error(parseApiError(err, t, t('meetings.admin.deleteError')))
  }
}

const columns = computed<DataTableColumns<MeetingRoom>>(() => [
  {
    title: t('meetings.admin.roomName'),
    key: 'name',
    sorter: (a, b) => a.name.localeCompare(b.name),
    defaultSortOrder: 'ascend',
    render: (row) => h('span', { style: 'font-weight: 500' }, row.name),
  },
  {
    title: t('meetings.admin.roomKind'),
    key: 'kind',
    width: 130,
    sorter: (a, b) => a.kind.localeCompare(b.kind),
    render: (row) => h(NTag, {
      size: 'small',
      type: row.kind === 'virtual' ? 'info' : 'default',
      bordered: false,
    }, () => row.kind === 'virtual'
      ? t('meetings.admin.roomKindVirtual')
      : t('meetings.admin.roomKindPhysical')),
  },
  {
    title: t('meetings.admin.roomEmail'),
    key: 'email',
    width: 220,
    sorter: (a, b) => (a.email ?? '').localeCompare(b.email ?? ''),
    render: (row) => row.email
      ? h('a', { href: `mailto:${row.email}`, style: 'font-size: 12px' }, row.email)
      : '—',
  },
  {
    title: t('meetings.admin.roomTimezone'),
    key: 'timezone',
    width: 180,
    sorter: (a, b) => a.timezone.localeCompare(b.timezone),
  },
  {
    title: t('meetings.admin.roomLink'),
    key: 'link',
    render: (row) => {
      // FE-1: рендерим ссылку только для безопасных схем (http/https/internal).
      const safe = row.link && isServiceLinkUrl(row.link) ? row.link : null
      if (!safe) return row.link ? row.link.slice(0, 40) + (row.link.length > 40 ? '…' : '') : '—'
      return h('a', { href: safe, target: '_blank', rel: 'noopener noreferrer', style: 'font-size: 12px' }, safe.slice(0, 40) + (safe.length > 40 ? '…' : ''))
    },
  },
  {
    title: t('meetings.admin.roomOrder'),
    key: 'sort_order',
    width: 100,
  },
  {
    title: t('meetings.admin.roomStatus'),
    key: 'is_active',
    width: 100,
    render: (row) => h(NTag, {
      type: row.is_active ? 'success' : 'default',
      size: 'small',
    }, () => row.is_active ? t('common.active') : t('common.inactive')),
  },
  {
    title: '',
    key: 'actions',
    width: 220,
    render: (row) => h(NSpace, { size: 'small', wrap: false, wrapItem: false }, () => [
      h(NButton, {
        size: 'tiny',
        onClick: () => openEditForm(row),
      }, () => t('common.edit')),
      h(NButton, {
        size: 'tiny',
        type: 'error',
        ghost: true,
        onClick: () => onDelete(row),
      }, () => t('common.delete')),
    ]),
  },
])
</script>

<style scoped>
.admin-rooms {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.admin-rooms__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.admin-rooms__title {
  font-size: 18px;
  font-weight: 600;
  margin: 0;
}
.admin-rooms__filters {
  display: flex;
  align-items: center;
  gap: 8px;
}
.admin-rooms__filter-label {
  font-size: 13px;
  color: var(--color-text);
}
</style>
