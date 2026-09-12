<template>
  <section>
    <div class="toolbar">
      <n-select
        v-model:value="selectedUserId"
        filterable
        clearable
        remote
        :options="userOptions"
        :loading="searching"
        :placeholder="t('learning.methodists.pickUser')"
        style="max-width: 420px"
        @search="searchUsers"
        @update:show="() => searchUsers('')"
      />
      <n-button
        type="primary"
        :disabled="!selectedUserId"
        :loading="assignMut.isPending.value"
        @click="assign"
      >
        {{ t('learning.methodists.assign') }}
      </n-button>
    </div>

    <n-data-table
      :columns="columns"
      :data="rows"
      :loading="query.isLoading.value"
      :row-key="(m: LearningAdmin) => m.user_id"
      :bordered="false"
      striped
    />
  </section>
</template>

<script setup lang="ts">
import { computed, h, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NButton,
  NDataTable,
  NIcon,
  NPopconfirm,
  NSelect,
  useMessage,
  type DataTableColumns,
} from 'naive-ui'
import { TrashOutline } from '@vicons/ionicons5'
import {
  useAssignMethodistMutation,
  useLearningAdminsQuery,
  useRevokeMethodistMutation,
} from '../../queries/learning'
import { fetchUsers } from '../../api/users'
import type { LearningAdmin } from '../../api/learning'
import { parseApiError } from '../../utils/parseApiError'
import { useRemoteSearch } from '../../composables/useRemoteSearch'
import { formatDate } from '../../utils/formatDate'

const { t, locale } = useI18n()
const message = useMessage()

const query = useLearningAdminsQuery()
const rows = computed<LearningAdmin[]>(() => query.data.value ?? [])
watch(query.error, (e) => {
  if (e) message.error(parseApiError(e, t))
})

const assignMut = useAssignMethodistMutation()
const revokeMut = useRevokeMethodistMutation()
watch(assignMut.error, (e) => {
  if (e) message.error(parseApiError(e, t))
})
watch(revokeMut.error, (e) => {
  if (e) message.error(parseApiError(e, t))
})

const selectedUserId = ref<string | null>(null)
const users = useRemoteSearch((q) => fetchUsers({ q, page_size: 20 }), {
  onError: (e) => message.error(parseApiError(e, t)),
})
const userOptions = users.options
const searching = users.searching
const searchUsers = users.search

async function assign() {
  if (!selectedUserId.value) return
  try {
    await assignMut.mutateAsync(selectedUserId.value)
    message.success(t('learning.methodists.assigned'))
    selectedUserId.value = null
  } catch {
    // ошибка уже показана в watch
  }
}

async function revoke(row: LearningAdmin) {
  try {
    await revokeMut.mutateAsync(row.user_id)
    message.success(t('learning.methodists.revoked'))
  } catch {
    // ошибка уже показана в watch
  }
}

const columns = computed<DataTableColumns<LearningAdmin>>(() => [
  { title: t('learning.methodists.colName'), key: 'full_name' },
  { title: t('learning.methodists.colEmail'), key: 'email', width: 280 },
  {
    title: t('learning.methodists.colAdded'),
    key: 'added_at',
    width: 160,
    render: (m) => formatDate(m.added_at, locale.value),
  },
  {
    title: '',
    key: 'actions',
    width: 120,
    render: (m) =>
      h(NPopconfirm, { onPositiveClick: () => revoke(m) }, {
        trigger: () =>
          h(
            NButton,
            {
              size: 'tiny',
              type: 'error',
              quaternary: true,
              loading: revokeMut.isPending.value,
            },
            {
              icon: () => h(NIcon, null, { default: () => h(TrashOutline) }),
              default: () => t('common.delete'),
            },
          ),
        default: () => t('learning.methodists.revokeConfirm'),
      }),
  },
])
</script>

<style scoped>
.toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
</style>
