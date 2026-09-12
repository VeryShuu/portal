<template>
  <div>
    <div class="tab-toolbar">
      <n-input
        v-model:value="subjectFilter"
        size="small"
        clearable
        :placeholder="t('files.share.admin.filterSubject')"
        style="width: 240px"
        @keyup.enter="applyFilters"
      />
      <n-checkbox
        v-model:checked="activeOnly"
        @update:checked="applyFilters"
      >
        {{ t('files.share.admin.activeOnly') }}
      </n-checkbox>
      <n-button
        size="small"
        @click="applyFilters"
      >
        {{ t('files.share.admin.apply') }}
      </n-button>
    </div>

    <n-data-table
      :columns="columns"
      :data="data?.items ?? []"
      :loading="isLoading"
      size="small"
      :bordered="false"
      remote
      :pagination="pagination"
      @update:page="onPage"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, h, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NCheckbox, NDataTable, NInput, NTag } from 'naive-ui'
import type { AdminFileShare } from '../../../api/files'
import { useAdminSharesQuery } from '../../../queries/files'

const { t } = useI18n()

const PAGE_SIZE = 50
const page = ref(1)
const subjectFilter = ref('')
const activeOnly = ref(false)

const appliedSubject = ref('')
const appliedActiveOnly = ref(false)

const queryParams = computed(() => ({
  subject_id: appliedSubject.value || undefined,
  active_only: appliedActiveOnly.value || undefined,
  limit: PAGE_SIZE,
  offset: (page.value - 1) * PAGE_SIZE,
}))

const { data, isLoading } = useAdminSharesQuery(queryParams)

const pagination = computed(() => ({
  page: page.value,
  pageSize: PAGE_SIZE,
  itemCount: data.value?.total ?? 0,
  showSizePicker: false,
}))

function applyFilters() {
  appliedSubject.value = subjectFilter.value.trim()
  appliedActiveOnly.value = activeOnly.value
  page.value = 1
}

function onPage(p: number) {
  page.value = p
}

function formatDate(dt: string | null): string {
  return dt ? new Date(dt).toLocaleString('ru-RU') : '—'
}

const permissionLabel = (p: string) =>
  ({ viewer: t('files.permission.viewer'), editor: t('files.permission.editor') }[p] ?? p)

const columns = computed(() => [
  {
    title: t('files.share.recipient'),
    key: 'subject_name',
    render: (row: AdminFileShare) =>
      h('span', {}, `${row.subject_type === 'group' ? '👥 ' : '👤 '}${row.subject_name}`),
  },
  {
    title: t('files.permissions.level'),
    key: 'permission',
    width: 100,
    render: (row: AdminFileShare) =>
      h(NTag, { size: 'small', bordered: false }, () => permissionLabel(row.permission)),
  },
  { title: t('files.share.admin.ncPath'), key: 'nc_path', ellipsis: { tooltip: true } },
  {
    title: t('files.share.sharedBy'),
    key: 'shared_by_name',
    render: (row: AdminFileShare) => row.shared_by_name ?? '—',
  },
  {
    title: t('files.share.admin.created'),
    key: 'created_at',
    width: 160,
    render: (row: AdminFileShare) => formatDate(row.created_at),
  },
  {
    title: t('files.share.expires'),
    key: 'expires_at',
    width: 120,
    render: (row: AdminFileShare) => formatDate(row.expires_at),
  },
  {
    title: t('files.share.admin.status'),
    key: 'revoked_at',
    width: 110,
    render: (row: AdminFileShare) =>
      row.revoked_at
        ? h(NTag, { size: 'small', type: 'error', bordered: false }, () =>
            t('files.share.admin.revoked')
          )
        : h(NTag, { size: 'small', type: 'success', bordered: false }, () =>
            t('files.share.admin.active')
          ),
  },
])
</script>

<style scoped>
.tab-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}
</style>
