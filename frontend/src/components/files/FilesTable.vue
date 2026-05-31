<template>
  <n-data-table
    :columns="tableColumns"
    :data="items"
    :row-key="(row: NCItem) => row.nc_path"
    :checked-row-keys="selectedKeys"
    :row-props="rowProps"
    size="small"
    :bordered="false"
    :single-line="false"
    @update:checked-row-keys="emit('update:selectedKeys', $event as string[])"
  />
</template>

<script setup lang="ts">
import { computed, h, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NDataTable, NTooltip, type DataTableColumns } from 'naive-ui'
import {
  downloadFile,
  fileIcon,
  formatFileSize,
  isCollaboraFile,
  isPreviewableImage,
  isPreviewablePdf,
  type NCItem,
} from '../../api/files'
import { useFileIconsStore } from '../../stores/fileIcons'

const props = defineProps<{
  items: NCItem[]
  loading: boolean
  selectedKeys: string[]
  canUpload: boolean
  canEdit: boolean
  canManage: boolean
  folderId: string | null
  openingCollaboraFile: string | null
}>()

const emit = defineEmits<{
  'update:selectedKeys': [keys: string[]]
  'row-click': [payload: { row: NCItem; index: number; event: MouseEvent }]
  'preview-image': [item: NCItem]
  'preview-pdf': [item: NCItem]
  'open-collabora': [item: NCItem]
  'delete-file': [item: NCItem]
  'share-file': [item: NCItem]
}>()

const { t } = useI18n()
const iconsStore = useFileIconsStore()

onMounted(() => {
  iconsStore.load()
})

function renderIcon(row: NCItem) {
  const icon = fileIcon(row, (ext) => iconsStore.iconUrlFor(ext))
  if (icon.kind === 'svg') {
    return h('img', {
      src: icon.url,
      alt: icon.alt,
      width: 20,
      height: 20,
      class: 'file-type-icon file-type-icon--svg',
      draggable: false,
    })
  }
  return h('span', { class: 'file-type-icon' }, icon.char)
}

function formatDateTime(dt: string | null): string {
  if (!dt) return '—'
  return new Date(dt).toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function getDownloadUrl(item: NCItem): string {
  if (!props.folderId) return '#'
  return downloadFile(props.folderId, item.name)
}

function dirFirst(a: NCItem, b: NCItem): number {
  if (a.is_dir && !b.is_dir) return -1
  if (!a.is_dir && b.is_dir) return 1
  return 0
}

const tableColumns = computed<DataTableColumns<NCItem>>(() => [
  {
    type: 'selection',
    disabled: (row: NCItem) => row.is_dir,
  },
  {
    key: 'name',
    title: t('files.table.name'),
    render(row) {
      return h('div', { class: 'files-cell-name' }, [
        renderIcon(row),
        h('span', { class: 'files-cell-name__text' }, row.name),
      ])
    },
    ellipsis: { tooltip: true },
    defaultSortOrder: 'ascend',
    sorter(a, b) {
      const d = dirFirst(a, b)
      if (d !== 0) return d
      return a.name.localeCompare(b.name, 'ru')
    },
  },
  {
    key: 'size_bytes',
    title: t('files.table.size'),
    width: 100,
    render(row) {
      return row.is_dir ? '—' : formatFileSize(row.size_bytes)
    },
    sorter(a, b) {
      const d = dirFirst(a, b)
      if (d !== 0) return d
      return (a.size_bytes ?? 0) - (b.size_bytes ?? 0)
    },
  },
  {
    key: 'uploaded_at',
    title: t('files.table.uploaded'),
    width: 160,
    render(row) {
      if (row.is_dir || !row.uploaded_at) return '—'
      const dateStr = formatDateTime(row.uploaded_at)
      if (!row.uploaded_by) return dateStr
      return h(NTooltip, {}, {
        trigger: () => h('span', { class: 'files-cell-date' }, dateStr),
        default: () => row.uploaded_by!.full_name,
      })
    },
    sorter(a, b) {
      const d = dirFirst(a, b)
      if (d !== 0) return d
      return (a.uploaded_at ?? '').localeCompare(b.uploaded_at ?? '')
    },
  },
  {
    key: 'last_modified',
    title: t('files.table.modified'),
    width: 160,
    render(row) {
      return row.is_dir ? '—' : formatDateTime(row.last_modified)
    },
    sorter(a, b) {
      const d = dirFirst(a, b)
      if (d !== 0) return d
      return (a.last_modified ?? '').localeCompare(b.last_modified ?? '')
    },
  },
  {
    key: 'actions',
    title: '',
    width: 400,
    render(row) {
      if (row.is_dir) return null
      const btns = []
      if (isPreviewableImage(row) || isPreviewablePdf(row)) {
        btns.push(
          h(NButton, {
            size: 'tiny',
            onClick: (e: MouseEvent) => {
              e.stopPropagation()
              isPreviewablePdf(row) ? emit('preview-pdf', row) : emit('preview-image', row)
            },
          }, { default: () => t('files.preview') })
        )
      }
      btns.push(
        h(NButton, {
          size: 'tiny',
          tag: 'a',
          href: getDownloadUrl(row),
          download: true,
          onClick: (e: MouseEvent) => e.stopPropagation(),
        }, { default: () => t('files.download') })
      )
      if (isCollaboraFile(row)) {
        const isOpening = props.openingCollaboraFile === row.name
        btns.push(
          h(NButton, {
            size: 'tiny',
            type: props.canEdit ? 'primary' : 'default',
            ghost: props.canEdit,
            loading: isOpening,
            disabled: isOpening,
            onClick: (e: MouseEvent) => { e.stopPropagation(); emit('open-collabora', row) },
          }, { default: () => props.canEdit ? t('files.edit') : t('files.view') })
        )
      }
      if (props.canManage) {
        btns.push(
          h(NButton, {
            size: 'tiny',
            onClick: (e: MouseEvent) => { e.stopPropagation(); emit('share-file', row) },
          }, { default: () => t('files.share.action') })
        )
      }
      if (props.canUpload) {
        btns.push(
          h(NButton, {
            size: 'tiny',
            type: 'error',
            ghost: true,
            onClick: (e: MouseEvent) => { e.stopPropagation(); emit('delete-file', row) },
          }, { default: () => t('common.delete') })
        )
      }
      return h('div', { class: 'files-cell-actions' }, btns)
    },
  },
])

function rowProps(row: NCItem, index: number) {
  return {
    onClick: (e: MouseEvent) => emit('row-click', { row, index, event: e }),
    class: row.is_dir ? 'files-row--dir' : '',
  }
}
</script>

<style scoped>
.file-type-icon {
  font-size: 18px;
  line-height: 1;
  margin-right: 8px;
  flex-shrink: 0;
}

.files-cell-name {
  display: flex;
  align-items: center;
  min-width: 0;
}

.files-cell-name__text {
  font-size: 14px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.files-cell-date {
  cursor: default;
  border-bottom: 1px dashed var(--n-text-color-3, #bbb);
}

.files-cell-actions {
  display: flex;
  gap: 6px;
  justify-content: flex-end;
}
</style>

<style>
.files-row--dir {
  cursor: pointer;
}
.files-row--dir:hover td {
  background: var(--n-hover-color, #f5f5f5) !important;
}
img.file-type-icon--svg {
  width: 20px;
  height: 20px;
  max-width: 20px;
  max-height: 20px;
  object-fit: contain;
  display: inline-block;
  vertical-align: middle;
  flex-shrink: 0;
}
.files-cell-name {
  display: inline-flex !important;
  align-items: center;
  min-width: 0;
  max-width: 100%;
  vertical-align: middle;
}
.files-cell-name .file-type-icon {
  margin-right: 10px;
}
.files-cell-name__text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.files-cell-actions {
  display: flex;
  flex-wrap: nowrap;
  gap: 6px;
  justify-content: flex-end;
  white-space: nowrap;
}
.files-cell-actions > * {
  flex-shrink: 0;
}
</style>
