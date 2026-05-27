<template>
  <div class="kb-trash">
    <div class="page-head u-page-head">
      <div class="page-head__left">
        <h1 class="u-page-head__title">
          {{ t('kb.trash.title') }}
        </h1>
        <div class="u-page-head__sub">
          {{ t('kb.trash.subtitle') }}
        </div>
      </div>
      <div class="page-head__right u-page-head__actions">
        <n-button
          quaternary
          @click="router.push({ name: 'kb' })"
        >
          ← {{ t('common.back') }}
        </n-button>
        <n-button
          :loading="refreshing"
          @click="reload()"
        >
          {{ t('common.refresh') }}
        </n-button>
        <n-button
          v-if="data && data.purge_due_count > 0"
          type="warning"
          :loading="bulkBusy"
          @click="confirmPurgeExpired"
        >
          {{ t('kb.trash.purgeExpired', { n: data.purge_due_count }) }}
        </n-button>
        <n-button
          v-if="data && data.total > 0"
          type="error"
          :loading="bulkBusy"
          @click="confirmPurgeAll"
        >
          {{ t('kb.trash.purgeAll') }}
        </n-button>
      </div>
    </div>

    <n-card
      v-if="data"
      size="small"
      class="kb-trash__retention"
    >
      <div class="kb-trash__retention-row">
        <div class="kb-trash__retention-text">
          <div class="kb-trash__retention-title">
            {{ t('kb.trash.retentionTitle') }}
          </div>
          <div class="kb-trash__retention-hint">
            {{ t('kb.trash.retentionEditHint') }}
          </div>
        </div>
        <div class="kb-trash__retention-controls">
          <n-input-number
            v-model:value="retentionDraft"
            :min="0"
            :max="3650"
            :disabled="retentionSaving"
            style="width:140px"
          />
          <span class="kb-trash__retention-unit">{{ t('kb.trash.retentionUnit') }}</span>
          <n-button
            type="primary"
            :loading="retentionSaving"
            :disabled="!retentionDirty"
            @click="saveRetention"
          >
            {{ t('common.save') }}
          </n-button>
        </div>
      </div>
    </n-card>

    <n-data-table
      :columns="columns"
      :data="rows"
      :loading="loading"
      :pagination="pagination"
      :remote="true"
      :bordered="false"
      size="small"
      style="margin-top:16px"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, h, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  NButton, NCard, NDataTable, NInputNumber, NPopconfirm, NTag, useDialog, useMessage,
  type DataTableColumns,
} from 'naive-ui'
import {
  fetchTrashArticles, restoreTrashArticle, purgeTrashArticle, purgeAllTrash,
  updateTrashRetention,
  type KbTrashItem, type KbTrashList,
} from '../api/kb'
import { parseApiError } from '../utils/parseApiError'

const { t, locale } = useI18n()
const router = useRouter()
const message = useMessage()
const dialog = useDialog()

const data = ref<KbTrashList | null>(null)
const loading = ref(false)
const refreshing = ref(false)
const bulkBusy = ref(false)
const page = ref(1)
const pageSize = ref(50)
const rowBusy = ref<Record<string, boolean>>({})
const retentionDraft = ref<number>(30)
const retentionSaving = ref(false)
const retentionDirty = computed(
  () => data.value != null && retentionDraft.value !== data.value.retention_days,
)

const rows = computed<KbTrashItem[]>(() => data.value?.items ?? [])

const pagination = computed(() => ({
  page: page.value,
  pageSize: pageSize.value,
  itemCount: data.value?.total ?? 0,
  showSizePicker: true,
  pageSizes: [25, 50, 100, 200],
  onChange: (p: number) => {
    page.value = p
    reload()
  },
  onUpdatePageSize: (size: number) => {
    pageSize.value = size
    page.value = 1
    reload()
  },
}))

function formatBytes(bytes: number): string {
  if (!bytes) return '—'
  const units = ['B', 'KB', 'MB', 'GB']
  let v = bytes
  let i = 0
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i++
  }
  return `${v.toFixed(v >= 10 || i === 0 ? 0 : 1)} ${units[i]}`
}

function formatDate(s: string): string {
  try {
    return new Date(s).toLocaleString(locale.value === 'ru' ? 'ru-RU' : 'en-US')
  } catch {
    return s
  }
}

const columns = computed<DataTableColumns<KbTrashItem>>(() => [
  {
    title: t('kb.trash.col.title'),
    key: 'title',
    minWidth: 240,
    render: (row) => h('div', { style: 'display:flex;flex-direction:column;gap:2px' }, [
      h('strong', row.title),
      row.section_title
        ? h('span', { style: 'font-size:12px;color:var(--color-text-secondary)' }, row.section_title)
        : null,
    ]),
  },
  {
    title: t('kb.trash.col.status'),
    key: 'status',
    width: 110,
    render: (row) => h(NTag, { size: 'small', bordered: false }, () => row.status),
  },
  {
    title: t('kb.trash.col.deletedAt'),
    key: 'deleted_at',
    width: 170,
    render: (row) => formatDate(row.deleted_at),
  },
  {
    title: t('kb.trash.col.deletedBy'),
    key: 'updated_by',
    width: 160,
    render: (row) => row.updated_by?.full_name || row.created_by?.full_name || '—',
  },
  {
    title: t('kb.trash.col.files'),
    key: 'files_count',
    width: 90,
    align: 'right',
    render: (row) => row.files_count,
  },
  {
    title: t('kb.trash.col.size'),
    key: 'size',
    width: 110,
    align: 'right',
    render: (row) => formatBytes(row.files_bytes + row.media_bytes),
  },
  {
    title: '',
    key: 'actions',
    width: 220,
    render: (row) => h('div', { style: 'display:flex;gap:8px;justify-content:flex-end' }, [
      h(NButton, {
        size: 'small',
        loading: rowBusy.value[row.id],
        onClick: () => onRestore(row),
      }, () => t('kb.trash.restore')),
      h(NPopconfirm, {
        positiveText: t('common.delete'),
        negativeText: t('common.cancel'),
        onPositiveClick: () => onPurge(row),
      }, {
        default: () => t('kb.trash.purgeConfirm', { title: row.title }),
        trigger: () => h(NButton, {
          size: 'small',
          type: 'error',
          loading: rowBusy.value[row.id],
        }, () => t('kb.trash.purge')),
      }),
    ]),
  },
])

async function reload(opts: { silent?: boolean } = {}) {
  if (opts.silent) refreshing.value = true
  else loading.value = true
  try {
    data.value = await fetchTrashArticles({
      limit: pageSize.value,
      offset: (page.value - 1) * pageSize.value,
    })
    if (!retentionSaving.value) {
      retentionDraft.value = data.value.retention_days
    }
  } catch (err) {
    message.error(parseApiError(err, t))
  } finally {
    loading.value = false
    refreshing.value = false
  }
}

async function saveRetention() {
  const value = retentionDraft.value
  if (typeof value !== 'number' || value < 0 || value > 3650) {
    message.error(t('kb.trash.retentionInvalid'))
    return
  }
  retentionSaving.value = true
  try {
    await updateTrashRetention(value)
    if (data.value) data.value = { ...data.value, retention_days: value }
    message.success(t('kb.trash.retentionSaved'))
    await reload({ silent: true })
  } catch (err) {
    message.error(parseApiError(err, t))
  } finally {
    retentionSaving.value = false
  }
}

async function onRestore(row: KbTrashItem) {
  rowBusy.value[row.id] = true
  try {
    await restoreTrashArticle(row.id)
    message.success(t('kb.trash.restored', { title: row.title }))
    await reload({ silent: true })
  } catch (err) {
    message.error(parseApiError(err, t))
  } finally {
    rowBusy.value[row.id] = false
  }
}

async function onPurge(row: KbTrashItem) {
  rowBusy.value[row.id] = true
  try {
    await purgeTrashArticle(row.id)
    message.success(t('kb.trash.purged', { title: row.title }))
    await reload({ silent: true })
  } catch (err) {
    message.error(parseApiError(err, t))
  } finally {
    rowBusy.value[row.id] = false
  }
}

function confirmPurgeAll() {
  dialog.warning({
    title: t('kb.trash.purgeAll'),
    content: t('kb.trash.purgeAllConfirm'),
    positiveText: t('common.delete'),
    negativeText: t('common.cancel'),
    onPositiveClick: async () => {
      bulkBusy.value = true
      try {
        const r = await purgeAllTrash(null)
        message.success(t('kb.trash.bulkPurged', { n: r.purged }))
        await reload({ silent: true })
      } catch (err) {
        message.error(parseApiError(err, t))
      } finally {
        bulkBusy.value = false
      }
    },
  })
}

function confirmPurgeExpired() {
  if (!data.value) return
  const days = data.value.retention_days
  dialog.warning({
    title: t('kb.trash.purgeExpiredTitle'),
    content: t('kb.trash.purgeExpiredConfirm', { days }),
    positiveText: t('common.delete'),
    negativeText: t('common.cancel'),
    onPositiveClick: async () => {
      bulkBusy.value = true
      try {
        const r = await purgeAllTrash(days)
        message.success(t('kb.trash.bulkPurged', { n: r.purged }))
        await reload({ silent: true })
      } catch (err) {
        message.error(parseApiError(err, t))
      } finally {
        bulkBusy.value = false
      }
    },
  })
}

watch(() => locale.value, () => { /* re-render via reactive columns */ })

reload()
</script>

<style scoped>
.kb-trash {
  padding: 16px 24px 32px;
}
.kb-trash__retention {
  margin-top: 4px;
}
.kb-trash__retention-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}
.kb-trash__retention-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 240px;
}
.kb-trash__retention-title {
  font-weight: 600;
}
.kb-trash__retention-hint {
  font-size: 12px;
  color: var(--color-text-secondary);
}
.kb-trash__retention-controls {
  display: flex;
  align-items: center;
  gap: 8px;
}
.kb-trash__retention-unit {
  font-size: 13px;
  color: var(--color-text-secondary);
}
</style>
