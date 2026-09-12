<template>
  <div class="shares-panel">
    <h2 class="shares-panel__title">
      {{ mode === 'my' ? t('files.share.mySharesTitle') : t('files.share.sharedWithMeTitle') }}
    </h2>

    <div
      v-if="loading"
      class="shares-panel__loading"
    >
      {{ t('common.loading') }}
    </div>

    <EmptyState
      v-else-if="!rows.length"
      variant="file"
      :title="mode === 'my' ? t('files.share.myEmpty') : t('files.share.sharedEmpty')"
    />

    <n-data-table
      v-else
      :columns="columns"
      :data="rows"
      size="small"
      :bordered="false"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, h, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NDataTable, NTag, useMessage } from 'naive-ui'
import {
  type MyFileShare,
  type SharedFile,
  downloadFile,
  fetchMyShares,
  fetchSharedWithMe,
  isCollaboraFile,
  openInCollabora,
  previewFile,
  revokeFileShare,
} from '../../api/files'
import EmptyState from '../EmptyState.vue'

const props = defineProps<{
  mode: 'my' | 'shared-with-me'
}>()

const { t } = useI18n()
const message = useMessage()

const myRows = ref<MyFileShare[]>([])
const sharedRows = ref<SharedFile[]>([])
const loading = ref(false)

const rows = computed<(MyFileShare | SharedFile)[]>(() =>
  props.mode === 'my' ? myRows.value : sharedRows.value
)

const permissionLabel = (p: string) =>
  ({ viewer: t('files.permission.viewer'), editor: t('files.permission.editor') }[p] ?? p)

function formatDate(dt: string | null): string {
  return dt ? new Date(dt).toLocaleDateString('ru-RU') : '—'
}

function isCollaboraName(name: string): boolean {
  return isCollaboraFile({ name, is_dir: false } as never)
}

async function load() {
  loading.value = true
  try {
    if (props.mode === 'my') {
      myRows.value = (await fetchMyShares()).items
    } else {
      sharedRows.value = (await fetchSharedWithMe()).items
    }
  } catch {
    message.error(t('files.share.error.load'))
  } finally {
    loading.value = false
  }
}

async function onRevoke(row: MyFileShare) {
  try {
    await revokeFileShare(row.folder_id, row.filename, row.id)
    message.success(t('files.share.revoked'))
    await load()
  } catch {
    message.error(t('files.share.error.revoke'))
  }
}

function onPreview(row: SharedFile) {
  window.open(previewFile(row.folder_id, row.filename), '_blank', 'noopener,noreferrer')
}

async function onOpenCollabora(row: SharedFile) {
  try {
    const res = await openInCollabora(row.folder_id, row.filename)
    window.open(res.url, '_blank', 'noopener,noreferrer')
  } catch {
    message.error(t('files.error.openCollabora'))
  }
}

const myColumns = computed(() => [
  { title: t('files.table.name'), key: 'filename', ellipsis: { tooltip: true } },
  { title: t('files.share.folder'), key: 'folder_name', ellipsis: { tooltip: true } },
  {
    title: t('files.share.recipient'),
    key: 'subject_name',
    render: (row: MyFileShare) =>
      h('span', {}, `${row.subject_type === 'group' ? '👥 ' : '👤 '}${row.subject_name}`),
  },
  {
    title: t('files.permissions.level'),
    key: 'permission',
    width: 110,
    render: (row: MyFileShare) =>
      h(NTag, { size: 'small', bordered: false }, () => permissionLabel(row.permission)),
  },
  {
    title: t('files.share.expires'),
    key: 'expires_at',
    width: 120,
    render: (row: MyFileShare) => formatDate(row.expires_at),
  },
  {
    title: '',
    key: 'actions',
    width: 90,
    render: (row: MyFileShare) =>
      h(
        NButton,
        { size: 'tiny', type: 'error', ghost: true, onClick: () => onRevoke(row) },
        () => t('files.share.revoke')
      ),
  },
])

const sharedColumns = computed(() => [
  { title: t('files.table.name'), key: 'filename', ellipsis: { tooltip: true } },
  { title: t('files.share.folder'), key: 'folder_name', ellipsis: { tooltip: true } },
  {
    title: t('files.share.sharedBy'),
    key: 'shared_by_name',
    render: (row: SharedFile) => row.shared_by_name ?? '—',
  },
  {
    title: t('files.permissions.level'),
    key: 'permission',
    width: 110,
    render: (row: SharedFile) =>
      h(NTag, { size: 'small', bordered: false }, () => permissionLabel(row.permission)),
  },
  {
    title: '',
    key: 'actions',
    width: 240,
    render: (row: SharedFile) => {
      const btns = [
        h(
          NButton,
          {
            size: 'tiny',
            tag: 'a',
            href: downloadFile(row.folder_id, row.filename),
            download: true,
          },
          () => t('files.download')
        ),
      ]
      if (isCollaboraName(row.filename)) {
        btns.push(
          h(
            NButton,
            { size: 'tiny', type: 'primary', ghost: true, onClick: () => onOpenCollabora(row) },
            () => (row.permission === 'editor' ? t('files.edit') : t('files.view'))
          )
        )
      } else {
        btns.push(
          h(NButton, { size: 'tiny', onClick: () => onPreview(row) }, () => t('files.preview'))
        )
      }
      return h('div', { class: 'files-cell-actions' }, btns)
    },
  },
])

const columns = computed(() => (props.mode === 'my' ? myColumns.value : sharedColumns.value))

onMounted(load)
watch(() => props.mode, load)
</script>

<style scoped>
.shares-panel {
  padding: 4px 0;
}
.shares-panel__title {
  font-size: 18px;
  font-weight: 600;
  margin: 0 0 16px;
}
.shares-panel__loading {
  padding: 20px 0;
  color: var(--n-text-color-3, #999);
}
</style>
