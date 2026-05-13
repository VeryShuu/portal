<template>
  <n-modal
    :show="show"
    :title="t('photos.permissions.title')"
    preset="card"
    style="width: 580px; max-width: 94vw"
    :mask-closable="true"
    @update:show="$emit('update:show', $event)"
  >
    <div v-if="loadingPerms" class="photos-perms-loading">{{ t('common.loading') }}</div>
    <template v-else-if="target">
      <n-data-table
        :columns="permColumns"
        :data="permsList"
        size="small"
        style="margin-bottom: 16px"
      />
      <n-divider />
      <h4 style="margin: 8px 0">{{ t('photos.permissions.grant') }}</h4>
      <div class="perm-grant-form">
        <n-auto-complete
          v-model:value="subjectSearchQuery"
          :options="subjectSearchOptions"
          :loading="subjectSearching"
          :placeholder="t('photos.permissions.searchPlaceholder')"
          clearable
          size="small"
          style="flex: 1"
          @update:value="onSubjectSearchChange"
          @select="onSubjectSelect"
        />
        <n-select
          v-model:value="newPerm.permission"
          :options="[
            { label: t('photos.permissions.perm_viewer'), value: 'viewer' },
            { label: t('photos.permissions.perm_uploader'), value: 'uploader' },
            { label: t('photos.permissions.perm_manager'), value: 'manager' },
          ]"
          size="small"
          style="width: 130px"
        />
        <n-button
          type="primary"
          :loading="permsAdding"
          :disabled="!newPerm.subject_id"
          @click="addPerm"
        >{{ t('photos.permissions.add') }}</n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { computed, h, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NAutoComplete,
  NButton,
  NDataTable,
  NDivider,
  NModal,
  NSelect,
  useMessage,
} from 'naive-ui'
import {
  fetchPermissions, grantPermission, revokePermission, searchSubjects,
  type PhotoFolder, type PhotoFolderTreeNode, type PhotoPermission,
  type PhotoSubjectSearchResult,
} from '@/api/photos'

const props = defineProps<{
  show: boolean
  target: PhotoFolder | PhotoFolderTreeNode | null
}>()

defineEmits<{
  (e: 'update:show', value: boolean): void
}>()

const { t } = useI18n()
const message = useMessage()

const permsList = ref<PhotoPermission[]>([])
const loadingPerms = ref(false)
const permsAdding = ref(false)
const newPerm = ref<{
  subject_type: 'user' | 'group'
  subject_id: string
  subject_name: string
  permission: 'viewer' | 'uploader' | 'manager'
}>({ subject_type: 'user', subject_id: '', subject_name: '', permission: 'viewer' })

const subjectSearchQuery = ref('')
const subjectSearching = ref(false)
const subjectSearchResults = ref<PhotoSubjectSearchResult[]>([])
const justSelected = ref(false)
let subjectSearchTimer: ReturnType<typeof setTimeout> | null = null

const subjectSearchOptions = computed(() =>
  subjectSearchResults.value.map((r) => ({
    label:
      r.subject_name +
      (r.email ? ` (${r.email})` : '') +
      (r.subject_type === 'group' ? ' 👥' : ' 👤'),
    value: r.subject_id,
  }))
)

const permissionLabel = (p: string) => ({
  viewer: t('photos.permissions.perm_viewer'),
  uploader: t('photos.permissions.perm_uploader'),
  manager: t('photos.permissions.perm_manager'),
}[p] ?? p)

const subjectTypeLabel = (s: string) => ({
  user: t('photos.permissions.subjectUser'),
  group: t('photos.permissions.subjectGroup'),
}[s] ?? s)

const permColumns = computed(() => [
  {
    title: t('photos.permissions.type'),
    key: 'subject_type',
    width: 80,
    render: (row: PhotoPermission) => subjectTypeLabel(row.subject_type),
  },
  { title: t('photos.permissions.name'), key: 'subject_name' },
  {
    title: t('photos.permissions.level'),
    key: 'permission',
    width: 100,
    render: (row: PhotoPermission) => permissionLabel(row.permission),
  },
  {
    title: '',
    key: 'actions',
    width: 80,
    render: (row: PhotoPermission) =>
      h(
        NButton,
        { size: 'tiny', type: 'error', ghost: true, onClick: () => revoke(row) },
        () => t('common.delete'),
      ),
  },
])

function resetGrantForm() {
  newPerm.value = { subject_type: 'user', subject_id: '', subject_name: '', permission: 'viewer' }
  subjectSearchQuery.value = ''
  subjectSearchResults.value = []
  justSelected.value = false
}

function onSubjectSearchChange(val: string) {
  if (justSelected.value) {
    justSelected.value = false
    return
  }
  newPerm.value.subject_id = ''
  newPerm.value.subject_name = ''
  if (subjectSearchTimer) clearTimeout(subjectSearchTimer)
  if (!val || val.length < 2) {
    subjectSearchResults.value = []
    return
  }
  subjectSearching.value = true
  subjectSearchTimer = setTimeout(async () => {
    try {
      subjectSearchResults.value = await searchSubjects(val)
    } catch {
      subjectSearchResults.value = []
    } finally {
      subjectSearching.value = false
    }
  }, 400)
}

function onSubjectSelect(val: string | number) {
  const found = subjectSearchResults.value.find((r) => r.subject_id === val)
  if (found) {
    justSelected.value = true
    newPerm.value.subject_type = found.subject_type
    newPerm.value.subject_id = found.subject_id
    newPerm.value.subject_name = found.subject_name
  }
}

async function loadPermissions() {
  if (!props.target) return
  loadingPerms.value = true
  try {
    const r = await fetchPermissions(props.target.id)
    permsList.value = r.items
  } catch {
    permsList.value = []
  } finally {
    loadingPerms.value = false
  }
}

watch(() => [props.show, props.target] as const, ([show, target]) => {
  if (!show || !target) return
  permsList.value = []
  resetGrantForm()
  loadPermissions()
})

async function addPerm() {
  if (!props.target) return
  if (!newPerm.value.subject_id || !newPerm.value.subject_name) {
    message.warning(t('photos.permissions.fieldsRequired'))
    return
  }
  permsAdding.value = true
  try {
    const created = await grantPermission(props.target.id, { ...newPerm.value })
    permsList.value = [...permsList.value.filter(p => p.subject_id !== created.subject_id), created]
    resetGrantForm()
    message.success(t('photos.permissions.granted'))
  } catch {
    message.error(t('errors.generic'))
  } finally {
    permsAdding.value = false
  }
}

async function revoke(p: PhotoPermission) {
  if (!props.target) return
  try {
    await revokePermission(props.target.id, p.subject_id)
    permsList.value = permsList.value.filter(x => x.id !== p.id)
    message.success(t('photos.permissions.revoked'))
  } catch {
    message.error(t('errors.generic'))
  }
}
</script>

<style scoped>
.photos-perms-loading {
  padding: 20px 0;
  color: var(--n-text-color-3, #999);
}

.perm-grant-form {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
</style>
