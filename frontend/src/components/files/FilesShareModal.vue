<template>
  <n-modal
    :show="show"
    :title="t('files.share.title', { name: filename ?? '' })"
    preset="card"
    style="width: 580px"
    @update:show="$emit('update:show', $event)"
  >
    <div class="share-grant-form">
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
        ]"
        size="small"
        style="width: 130px"
      />
    </div>
    <div class="share-ttl-row">
      <span class="share-ttl-label">{{ t('files.share.ttlLabel') }}</span>
      <n-input-number
        v-model:value="expiresInDays"
        :min="1"
        :max="3650"
        size="small"
        clearable
        :placeholder="t('files.share.ttlNever')"
        style="width: 160px"
      />
      <n-button
        type="primary"
        size="small"
        :loading="granting"
        :disabled="!grantForm.subject_id"
        @click="submitShare"
      >
        {{ t('files.share.add') }}
      </n-button>
    </div>
    <div
      v-if="isAllUsersSelected"
      class="share-warn"
    >
      {{ t('files.share.allUsersWarn') }}
    </div>

    <n-divider style="margin: 14px 0" />

    <h4 style="margin: 8px 0">
      {{ t('files.share.currentList') }}
    </h4>
    <div
      v-if="loadingShares"
      class="share-loading"
    >
      {{ t('common.loading') }}
    </div>
    <template v-else>
      <div
        v-for="s in shares"
        :key="s.id"
        class="share-row"
      >
        <span class="share-icon">{{ s.subject_type === 'group' ? '👥' : '👤' }}</span>
        <span class="share-name">{{ s.subject_name }}</span>
        <n-tag
          size="small"
          :bordered="false"
          :type="s.permission === 'editor' ? 'warning' : 'default'"
        >
          {{ permissionLabel(s.permission) }}
        </n-tag>
        <span
          v-if="s.expires_at"
          class="share-ttl"
        >{{ t('files.share.until', { date: formatDate(s.expires_at) }) }}</span>
        <n-button
          size="small"
          type="error"
          text
          @click="revokeShare(s.id)"
        >
          ✕
        </n-button>
      </div>
      <div
        v-if="!shares.length"
        class="share-empty"
      >
        {{ t('files.share.empty') }}
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NAutoComplete,
  NButton,
  NDivider,
  NInputNumber,
  NModal,
  NSelect,
  NTag,
  useMessage,
} from 'naive-ui'
import {
  type FileSharePublic,
  type FilesSubjectSearchResult,
  createFileShare,
  fetchFileShares,
  revokeFileShare,
  searchFilesSubjects,
} from '../../api/files'

const ALL_USERS_SUBJECT_ID = '__all_users__'

const props = defineProps<{
  show: boolean
  folderId: string | null
  filename: string | null
}>()

defineEmits<{
  'update:show': [v: boolean]
}>()

const { t } = useI18n()
const message = useMessage()

const shares = ref<FileSharePublic[]>([])
const loadingShares = ref(false)
const granting = ref(false)
const expiresInDays = ref<number | null>(null)

const grantForm = ref({
  subject_type: 'user' as 'user' | 'group',
  subject_id: '',
  subject_name: '',
  permission: 'viewer' as 'viewer' | 'editor',
})

const subjectSearchQuery = ref('')
const subjectSearching = ref(false)
const justSelected = ref(false)
const subjectSearchResults = ref<FilesSubjectSearchResult[]>([])

const subjectSearchOptions = computed(() =>
  subjectSearchResults.value.map((r) => ({
    label:
      r.subject_name +
      (r.email ? ` (${r.email})` : '') +
      (r.subject_type === 'group' ? ' 👥' : ' 👤'),
    value: r.subject_id,
  }))
)

const isAllUsersSelected = computed(() => grantForm.value.subject_id === ALL_USERS_SUBJECT_ID)

const permissionLabel = (p: string) =>
  ({ viewer: t('files.permission.viewer'), editor: t('files.permission.editor') }[p] ?? p)

function formatDate(dt: string): string {
  return new Date(dt).toLocaleDateString('ru-RU')
}

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
      subjectSearchResults.value = await searchFilesSubjects(val)
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
    grantForm.value.subject_type = found.subject_type
    grantForm.value.subject_id = found.subject_id
    grantForm.value.subject_name = found.subject_name
  }
}

async function loadShares() {
  if (!props.folderId || !props.filename) return
  loadingShares.value = true
  try {
    const data = await fetchFileShares(props.folderId, props.filename)
    shares.value = data.items
  } catch {
    message.error(t('files.share.error.load'))
  } finally {
    loadingShares.value = false
  }
}

async function submitShare() {
  if (!props.folderId || !props.filename || !grantForm.value.subject_id) return
  granting.value = true
  try {
    await createFileShare(props.folderId, props.filename, {
      subject_type: grantForm.value.subject_type,
      subject_id: grantForm.value.subject_id,
      subject_name: grantForm.value.subject_name,
      permission: grantForm.value.permission,
      expires_in_days: expiresInDays.value ?? undefined,
    })
    message.success(t('files.share.created'))
    resetForm()
    await loadShares()
  } catch {
    message.error(t('files.share.error.create'))
  } finally {
    granting.value = false
  }
}

async function revokeShare(shareId: string) {
  if (!props.folderId || !props.filename) return
  try {
    await revokeFileShare(props.folderId, props.filename, shareId)
    message.success(t('files.share.revoked'))
    await loadShares()
  } catch {
    message.error(t('files.share.error.revoke'))
  }
}

function resetForm() {
  grantForm.value = { subject_type: 'user', subject_id: '', subject_name: '', permission: 'viewer' }
  subjectSearchQuery.value = ''
  subjectSearchResults.value = []
  expiresInDays.value = null
  justSelected.value = false
}

watch(
  () => props.show,
  (v) => {
    if (v) {
      resetForm()
      loadShares()
    }
  }
)
</script>

<style scoped>
.share-grant-form {
  display: flex;
  gap: 8px;
  align-items: center;
}
.share-ttl-row {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-top: 10px;
}
.share-ttl-label {
  font-size: 13px;
  color: var(--n-text-color-3, #999);
}
.share-warn {
  margin-top: 10px;
  font-size: 13px;
  color: var(--n-color-warning, #f0a020);
}
.share-loading {
  padding: 12px 0;
  color: var(--n-text-color-3, #999);
}
.share-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
}
.share-name {
  flex: 1;
}
.share-ttl {
  font-size: 12px;
  color: var(--n-text-color-3, #999);
}
.share-empty {
  padding: 8px 0;
  color: var(--n-text-color-3, #999);
}
</style>
