<template>
  <n-modal
    v-model:show="show"
    preset="card"
    :title="t('kb.permissions.title')"
    style="max-width:560px"
  >
    <div class="perms-wrap">
      <div
        v-if="inheritToggle !== undefined"
        class="inherit-row"
      >
        <n-switch
          v-model:value="localInherit"
          @update:value="onToggleInherit"
        />
        <span class="inherit-label">{{ inheritLabel }}</span>
      </div>

      <div class="perms-list">
        <div
          v-for="p in permissions"
          :key="p.id"
          class="perm-row"
        >
          <span class="perm-icon">{{ p.subject_type === 'group' ? '👥' : '👤' }}</span>
          <span class="perm-name">{{ p.subject_name }}</span>
          <span
            v-if="p.email"
            class="perm-email"
          >{{ p.email }}</span>
          <n-select
            size="small"
            :value="p.permission"
            :options="permOptions"
            style="width:110px"
            @update:value="(val: string) => updatePerm(p, val)"
          />
          <n-button
            size="small"
            type="error"
            text
            @click="deletePerm(p.subject_id)"
          >
            ✕
          </n-button>
        </div>
        <div
          v-if="!permissions.length"
          class="perms-empty"
        >
          {{ t('kb.permissions.empty') }}
        </div>
      </div>

      <div class="add-row">
        <n-auto-complete
          v-model:value="searchQuery"
          :options="searchOptions"
          :loading="searching"
          :placeholder="t('kb.permissions.searchPlaceholder')"
          clearable
          size="small"
          style="flex:1"
          @update:value="onSearchChange"
          @select="onSelectSubject"
        />
        <n-select
          v-model:value="newPermLevel"
          :options="permOptions"
          size="small"
          style="width:110px"
        />
        <n-button
          type="primary"
          size="small"
          :disabled="!selectedSubject"
          @click="addPerm"
        >
          {{ t('kb.permissions.add') }}
        </n-button>
      </div>
    </div>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import { NModal, NSwitch, NSelect, NButton, NAutoComplete } from 'naive-ui'
import { api } from '@/api'

const props = defineProps<{
  modelValue: boolean
  resourceType: 'section' | 'article'
  resourceId: string
  inheritPermissions?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [v: boolean]
  'inheritChanged': [v: boolean]
}>()

const { t } = useI18n()
const message = useMessage()

const show = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

interface PermEntry {
  id: string
  subject_type: string
  subject_id: string
  subject_name: string
  email?: string
  permission: string
}

interface SubjectOption {
  label: string
  value: string
  raw: { subject_type: string; subject_id: string; subject_name: string; email?: string }
}

const permissions = ref<PermEntry[]>([])
const localInherit = ref(props.inheritPermissions ?? true)
const inheritToggle = computed(() => props.inheritPermissions !== undefined ? localInherit.value : undefined)

const inheritLabel = computed(() =>
  props.resourceType === 'section'
    ? t('kb.permissions.inheritFromParentSection')
    : t('kb.permissions.inheritFromSection'),
)

const searchQuery = ref('')
const searching = ref(false)
const searchResults = ref<SubjectOption[]>([])
const selectedSubject = ref<SubjectOption['raw'] | null>(null)
const newPermLevel = ref('viewer')
const justSelected = ref(false)

const permOptions = computed(() => [
  { label: t('kb.permissions.permViewer'), value: 'viewer' },
  { label: t('kb.permissions.permEditor'), value: 'editor' },
  { label: t('kb.permissions.permManager'), value: 'manager' },
])

const searchOptions = computed(() =>
  searchResults.value.map((r) => ({ label: r.label, value: r.value }))
)

watch(() => props.modelValue, (v) => {
  if (v) loadPerms()
})

watch(() => props.inheritPermissions, (v) => {
  if (v !== undefined) localInherit.value = v
})

async function loadPerms() {
  try {
    const url = props.resourceType === 'section'
      ? `/kb/sections/${props.resourceId}/permissions`
      : `/kb/articles/${props.resourceId}/permissions`
    const data = await api<{ items: PermEntry[] }>(url)
    permissions.value = data.items
  } catch {
    message.error(t('common.loadError'))
  }
}

let searchTimer: ReturnType<typeof setTimeout> | null = null
function onSearchChange(val: string) {
  if (justSelected.value) {
    justSelected.value = false
    return
  }
  selectedSubject.value = null
  if (searchTimer) clearTimeout(searchTimer)
  if (!val || val.length < 2) { searchResults.value = []; return }
  searching.value = true
  searchTimer = setTimeout(async () => {
    try {
      const res = await api<Array<{
        subject_type: string; subject_id: string; subject_name: string; email?: string
      }>>(`/kb/users/search?q=${encodeURIComponent(val)}`)
      searchResults.value = res.map((r) => ({
        label: r.subject_name + (r.email ? ` (${r.email})` : '') + (r.subject_type === 'group' ? ' 👥' : ' 👤'),
        value: r.subject_id,
        raw: r,
      }))
    } catch {
      searchResults.value = []
    } finally {
      searching.value = false
    }
  }, 400)
}

function onSelectSubject(val: string) {
  const found = searchResults.value.find((r) => r.value === val)
  if (found) {
    justSelected.value = true
    selectedSubject.value = found.raw
    searchQuery.value = found.label
  }
}

async function addPerm() {
  if (!selectedSubject.value) return
  const url = props.resourceType === 'section'
    ? `/kb/sections/${props.resourceId}/permissions`
    : `/kb/articles/${props.resourceId}/permissions`
  try {
    await api(url, {
      method: 'POST',
      body: { ...selectedSubject.value, permission: newPermLevel.value },
    })
    searchQuery.value = ''
    selectedSubject.value = null
    searchResults.value = []
    justSelected.value = false
    await loadPerms()
    message.success(t('kb.permissions.addedSuccess'))
  } catch {
    message.error(t('common.saveError'))
  }
}

async function updatePerm(p: PermEntry, newPerm: string) {
  const url = props.resourceType === 'section'
    ? `/kb/sections/${props.resourceId}/permissions`
    : `/kb/articles/${props.resourceId}/permissions`
  try {
    await api(url, {
      method: 'POST',
      body: {
        subject_type: p.subject_type,
        subject_id: p.subject_id,
        subject_name: p.subject_name,
        permission: newPerm,
      },
    })
    await loadPerms()
  } catch {
    message.error(t('common.saveError'))
  }
}

async function deletePerm(subjectId: string) {
  const url = props.resourceType === 'section'
    ? `/kb/sections/${props.resourceId}/permissions/${subjectId}`
    : `/kb/articles/${props.resourceId}/permissions/${subjectId}`
  try {
    await api(url, { method: 'DELETE' })
    await loadPerms()
    message.success(t('kb.permissions.revokedSuccess'))
  } catch {
    message.error(t('common.saveError'))
  }
}

async function onToggleInherit(val: boolean) {
  const url = props.resourceType === 'section'
    ? `/kb/sections/${props.resourceId}/inherit`
    : `/kb/articles/${props.resourceId}/inherit`
  try {
    await api(url, {
      method: 'PATCH',
      body: { inherit_permissions: val },
    })
    emit('inheritChanged', val)
    await loadPerms()
  } catch {
    message.error(t('common.saveError'))
    localInherit.value = !val
  }
}
</script>

<style scoped>
.perms-wrap { display: flex; flex-direction: column; gap: 16px; }
.inherit-row { display: flex; align-items: center; gap: 8px; }
.inherit-label { font-size: 14px; color: var(--n-text-color-2, #666); }
.perms-list { display: flex; flex-direction: column; gap: 6px; min-height: 40px; }
.perm-row { display: flex; align-items: center; gap: 8px; padding: 4px 0; }
.perm-icon { font-size: 16px; }
.perm-name { flex: 1; font-size: 14px; font-weight: 500; }
.perm-email { font-size: 12px; color: var(--n-text-color-3, #999); }
.perms-empty { font-size: 13px; color: var(--n-text-color-3, #999); padding: 8px 0; }
.add-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
</style>
