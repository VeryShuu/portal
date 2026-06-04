<template>
  <div class="directory-tab">
    <div class="directory-tab__bar">
      <n-input
        :value="searchInput"
        :placeholder="t('directories.searchPlaceholder')"
        clearable
        class="directory-tab__search"
        @update:value="onSearchInput"
      >
        <template #prefix>
          <n-icon><SearchOutline /></n-icon>
        </template>
      </n-input>

      <div class="directory-tab__actions">
        <n-button
          v-if="canEdit"
          type="primary"
          @click="openCreate"
        >
          <template #icon>
            <n-icon><AddOutline /></n-icon>
          </template>
          {{ t('directories.addEntry') }}
        </n-button>
        <n-dropdown
          trigger="click"
          :options="exportOptions"
          @select="onExport"
        >
          <n-button quaternary>
            <template #icon>
              <n-icon><DownloadOutline /></n-icon>
            </template>
            {{ t('directories.export') }}
          </n-button>
        </n-dropdown>
        <n-button
          v-if="canEdit"
          quaternary
          circle
          :title="t('directories.admin.manage')"
          @click="manage.open('directory')"
        >
          <template #icon>
            <n-icon><SettingsOutline /></n-icon>
          </template>
        </n-button>
      </div>
    </div>

    <div
      v-if="isLoading"
      class="directory-grid"
    >
      <SkeletonCard
        v-for="i in 6"
        :key="`sk-${i}`"
        variant="article"
      />
    </div>

    <EmptyState
      v-else-if="!entries.length"
      variant="search"
      :title="t('directories.empty')"
      :description="t('directories.emptyHint')"
    />

    <div
      v-else
      class="directory-grid"
    >
      <EntryCard
        v-for="entry in entries"
        :key="entry.id"
        :entry="entry"
        :directory="directory"
        :can-edit="canEdit"
        :hl="hl"
        :lang="lang"
        @edit="openEdit"
      />
    </div>

    <EntryEditDrawer
      v-if="canEdit"
      :show="drawerOpen"
      :directory="directory"
      :entry="editingEntry"
      :lang="lang"
      @close="drawerOpen = false"
      @saved="refetch"
    />

    <n-drawer
      v-if="canEdit"
      :show="manage.is('directory')"
      :width="760"
      placement="right"
      @update:show="(v: boolean) => { if (!v) manage.close() }"
    >
      <n-drawer-content
        :title="t('directories.admin.manage')"
        closable
      >
        <DirectorySettings />
      </n-drawer-content>
    </n-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NButton, NDrawer, NDrawerContent, NDropdown, NIcon, NInput,
} from 'naive-ui'
import {
  AddOutline, DownloadOutline, SearchOutline, SettingsOutline,
} from '@vicons/ionicons5'
import EmptyState from '../../components/EmptyState.vue'
import SkeletonCard from '../../components/SkeletonCard.vue'
import EntryCard from '../../components/directories/EntryCard.vue'
import EntryEditDrawer from '../../components/admin/EntryEditDrawer.vue'
import DirectorySettings from '../../components/admin/DirectorySettings.vue'
import type { DirectoryPublic, EntryPublic, ExportFormat } from '../../api/directories'
import { buildEntriesExportUrl } from '../../api/directories'
import { useDirectoryEntriesQuery } from '../../queries/directories'
import { useManageDrawer } from '../../composables/useManageDrawer'
import { useAuthStore } from '../../stores/auth'

const props = defineProps<{
  directory: DirectoryPublic
  lang?: 'ru' | 'en'
}>()

const { t } = useI18n()
const auth = useAuthStore()
const manage = useManageDrawer(['directory'])

const canEdit = computed(() => auth.isAdmin || auth.isEditor)

const searchInput = ref('')
const q = ref('')
let debounce: ReturnType<typeof setTimeout> | null = null

function onSearchInput(v: string) {
  searchInput.value = v
  if (debounce) clearTimeout(debounce)
  debounce = setTimeout(() => {
    q.value = v.trim()
  }, 300)
}

const slug = computed(() => props.directory.slug)
const params = computed(() => ({ q: q.value || undefined, limit: 200, offset: 0 }))

const entriesQuery = useDirectoryEntriesQuery(slug, params)
const entries = computed<EntryPublic[]>(() => entriesQuery.data.value?.items ?? [])
const isLoading = computed(() => entriesQuery.isLoading.value && !entriesQuery.data.value)

function refetch() {
  entriesQuery.refetch()
}

const drawerOpen = ref(false)
const editingEntry = ref<EntryPublic | null>(null)

function openCreate() {
  editingEntry.value = null
  drawerOpen.value = true
}

function openEdit(entry: EntryPublic) {
  editingEntry.value = entry
  drawerOpen.value = true
}

function hl(text: string | null | undefined): string {
  return text ?? ''
}

const exportOptions = computed(() => [
  { label: 'CSV', key: 'csv' },
  { label: 'XLSX', key: 'xlsx' },
  { label: 'PDF', key: 'pdf' },
])

function onExport(format: string) {
  window.location.assign(buildEntriesExportUrl(slug.value, format as ExportFormat))
}

watch(slug, () => {
  searchInput.value = ''
  q.value = ''
})
</script>

<style scoped>
.directory-tab {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.directory-tab__bar {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}
.directory-tab__search {
  flex: 1;
  min-width: 220px;
  max-width: 420px;
}
.directory-tab__actions {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-left: auto;
}
.directory-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
}
</style>
