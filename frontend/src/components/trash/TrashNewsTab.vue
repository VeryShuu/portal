<template>
  <div class="trash-news-tab">
    <n-data-table
      v-if="total > 0 || loading"
      :columns="columns"
      :data="items"
      :loading="loading"
      :pagination="false"
      :bordered="false"
      size="small"
    />
    <EmptyState v-else variant="news" :title="t('trash.empty')" />

    <div v-if="total > pageSize" class="trash-news-tab__pagination">
      <n-pagination
        v-model:page="page"
        :page-count="Math.ceil(total / pageSize)"
        :page-size="pageSize"
        show-size-picker
        :page-sizes="[20, 50, 100]"
        @update:page="load"
        @update:page-size="onPageSizeChange"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { h, ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NDataTable, NPagination, NButton, NPopconfirm, NSpace, useMessage,
  type DataTableColumns,
} from 'naive-ui'
import { NIcon } from 'naive-ui'
import { RefreshOutline, TrashBinOutline } from '@vicons/ionicons5'
import { listTrashNews, restoreNews, purgeNews, type NewsTrashItem } from '../../api/news'
import { formatDate } from '@/utils/formatDate'
import EmptyState from '../EmptyState.vue'

const { t, locale } = useI18n()
const message = useMessage()

const items = ref<NewsTrashItem[]>([])
const total = ref(0)
const loading = ref(false)
const page = ref(1)
const pageSize = ref(20)

async function load() {
  loading.value = true
  try {
    const res = await listTrashNews({ page: page.value, page_size: pageSize.value })
    items.value = res.items
    total.value = res.total
  } catch {
    message.error(t('trash.toast.error'))
  } finally {
    loading.value = false
  }
}

function onPageSizeChange(size: number) {
  pageSize.value = size
  page.value = 1
  load()
}

async function handleRestore(id: string) {
  try {
    await restoreNews(id)
    message.success(t('trash.toast.restored'))
    await load()
  } catch {
    message.error(t('trash.toast.error'))
  }
}

async function handlePurge(id: string) {
  try {
    await purgeNews(id)
    message.success(t('trash.toast.purged'))
    await load()
  } catch {
    message.error(t('trash.toast.error'))
  }
}

const columns: DataTableColumns<NewsTrashItem> = [
  {
    title: () => t('trash.news.columns.title'),
    key: 'title',
    ellipsis: { tooltip: true },
  },
  {
    title: () => t('trash.news.columns.author'),
    key: 'author',
    width: 160,
    render: (row) => row.author?.full_name ?? '—',
  },
  {
    title: () => t('trash.news.columns.previousStatus'),
    key: 'previous_status',
    width: 160,
    render: (row) => row.previous_status ?? '—',
  },
  {
    title: () => t('trash.news.columns.deletedAt'),
    key: 'deleted_at',
    width: 180,
    render: (row) => formatDate(row.deleted_at, locale.value),
  },
  {
    title: () => t('trash.news.columns.actions'),
    key: 'actions',
    width: 220,
    render: (row) =>
      h(NSpace, { size: 'small' }, {
        default: () => [
          h(
            NPopconfirm,
            { onPositiveClick: () => handleRestore(row.id) },
            {
              trigger: () =>
                h(
                  NButton,
                  { size: 'small', quaternary: true },
                  {
                    default: () => t('trash.actions.restore'),
                    icon: () => h(NIcon, null, { default: () => h(RefreshOutline) }),
                  },
                ),
              default: () => t('trash.confirm.restore'),
            },
          ),
          h(
            NPopconfirm,
            { onPositiveClick: () => handlePurge(row.id) },
            {
              trigger: () =>
                h(
                  NButton,
                  { size: 'small', type: 'error', quaternary: true },
                  {
                    default: () => t('trash.actions.purge'),
                    icon: () => h(NIcon, null, { default: () => h(TrashBinOutline) }),
                  },
                ),
              default: () => t('trash.confirm.purge'),
            },
          ),
        ],
      }),
  },
]

onMounted(load)
</script>

<style scoped>
.trash-news-tab__pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
