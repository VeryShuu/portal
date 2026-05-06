<template>
  <n-modal
    :show="show"
    :title="t('files.permissions.title')"
    preset="card"
    style="width: 580px"
    @update:show="$emit('update:show', $event)"
  >
    <div v-if="loadingPerms" class="files-perms-loading">{{ t('common.loading') }}</div>
    <template v-else>
      <n-data-table
        :columns="permColumns"
        :data="permissions"
        size="small"
        style="margin-bottom: 16px"
      />
      <n-divider />
      <h4 style="margin: 8px 0">{{ t('files.permissions.grant') }}</h4>
      <div class="perm-grant-form">
        <n-auto-complete
          v-model:value="subjectSearchQuery"
          :options="subjectSearchOptions"
          :loading="subjectSearching"
          :placeholder="t('files.permissions.searchPlaceholder')"
          clearable
          size="small"
          style="flex: 1"
          @update:value="onSubjectSearchChange"
          @select="onSubjectSelect"
        />
        <n-select
          v-model:value="grantForm.permission"
          :options="[
            { label: t('files.permission.viewer'), value: 'viewer' },
            { label: t('files.permission.editor'), value: 'editor' },
            { label: t('files.permission.manager'), value: 'manager' },
          ]"
          style="width: 130px"
        />
        <n-button
          type="primary"
          :loading="granting"
          :disabled="!grantForm.subject_id"
          @click="submitGrant"
        >{{ t('files.permissions.add') }}</n-button>
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
import { api } from '../../api'
import {
  type FilePermission,
  fetchPermissions,
  grantPermission,
  revokePermission,
} from '../../api/files'

const props = defineProps<{
  show: boolean
  folderId: string | null
}>()

defineEmits<{ 'update:show': [v: boolean] }>()

const { t } = useI18n()
const message = useMessage()

const permissions = ref<FilePermission[]>([])
const loadingPerms = ref(false)
const granting = ref(false)

const grantForm = ref({
  subject_type: 'user' as 'user' | 'group',
  subject_id: '',
  subject_name: '',
  permission: 'viewer' as 'viewer' | 'editor' | 'manager',
})

const subjectSearchQuery = ref('')
const subjectSearching = ref(false)
const justSelected = ref(false)

interface SubjectResult {
  subject_type: string
  subject_id: string
  subject_name: string
  email?: string
}

const subjectSearchResults = ref<SubjectResult[]>([])

const subjectSearchOptions = computed(() =>
  subjectSearchResults.value.map((r) => ({
    label: r.subject_name + (r.email ? ` (${r.email})` : '') + (r.subject_type === 'group' ? ' 👥' : ' 👤'),
    value: r.subject_id,
  }))
)

let subjectSearchTimer: ReturnType<typeof setTimeout> | null = null

function onSubjectSearchChange(val: string) {
  if (justSelected.value) {
    justSelected.value = false
    return
  }
  grantForm.value.subject_id = ''
  grantForm.value.subject_name = ''
  if (subjectSearchTimer) clearTimeout(subjectSearchTimer)
  if (!val || val.length < 2) {
    subjectSearchResults.value = []
    return
  }
  subjectSearching.value = true
  subjectSearchTimer = setTimeout(async () => {
    try {
      const res = await api<SubjectResult[]>(`/files/users/search?q=${encodeURIComponent(val)}`)
      subjectSearchResults.value = res
    } catch {
      subjectSearchResults.value = []
    } finally {
      subjectSearching.value = false
    }
  }, 400)
}

function onSubjectSelect(val: string) {
  const found = subjectSearchResults.value.find((r) => r.subject_id === val)
  if (found) {
    justSelected.value = true
    grantForm.value.subject_type = found.subject_type as 'user' | 'group'
    grantForm.value.subject_id = found.subject_id
    grantForm.value.subject_name = found.subject_name
  }
}

const permColumns = computed(() => [
  { title: t('files.permissions.type'), key: 'subject_type', width: 80 },
  { title: t('files.permissions.name'), key: 'subject_name' },
  { title: t('files.permissions.level'), key: 'permission', width: 100 },
  {
    title: '',
    key: 'actions',
    width: 80,
    render: (row: FilePermission) =>
      h(NButton, { size: 'tiny', type: 'error', ghost: true, onClick: () => revokePermHandler(row) }, () => t('common.delete')),
  },
])

async function loadPermissions() {
  if (!props.folderId) return
  loadingPerms.value = true
  try {
    const data = await fetchPermissions(props.folderId)
    permissions.value = data.items
  } catch {
    message.error(t('files.error.loadPerms'))
  } finally {
    loadingPerms.value = false
  }
}

async function submitGrant() {
  if (!props.folderId || !grantForm.value.subject_id || !grantForm.value.subject_name) return
  granting.value = true
  try {
    await grantPermission(props.folderId, grantForm.value)
    message.success(t('files.permissions.granted'))
    await loadPermissions()
    grantForm.value.subject_id = ''
    grantForm.value.subject_name = ''
    subjectSearchQuery.value = ''
    subjectSearchResults.value = []
    justSelected.value = false
  } catch {
    message.error(t('files.error.grantPerm'))
  } finally {
    granting.value = false
  }
}

async function revokePermHandler(perm: FilePermission) {
  if (!props.folderId) return
  try {
    await revokePermission(props.folderId, perm.id)
    message.success(t('files.permissions.revoked'))
    await loadPermissions()
  } catch {
    message.error(t('files.error.revokePerm'))
  }
}

watch(
  () => props.show,
  (v) => {
    if (v) {
      grantForm.value = { subject_type: 'user', subject_id: '', subject_name: '', permission: 'viewer' }
      subjectSearchQuery.value = ''
      subjectSearchResults.value = []
      justSelected.value = false
      loadPermissions()
    }
  },
)
</script>

<style scoped>
.files-perms-loading {
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
