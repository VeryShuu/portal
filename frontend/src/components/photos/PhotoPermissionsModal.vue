<template>
  <n-modal
    :show="show"
    preset="card"
    :title="t('photos.permissions.title')"
    style="width:540px;max-width:94vw"
    :mask-closable="true"
    @update:show="$emit('update:show', $event)"
  >
    <div v-if="target">
      <p class="perms-target"><strong>{{ target.name }}</strong></p>
      <ul v-if="permsList.length" class="perms-list">
        <li v-for="p in permsList" :key="p.id" class="perms-row">
          <span>{{ p.subject_name }} <em>({{ t(`photos.permissions.perm_${p.permission}`) }})</em></span>
          <n-button size="tiny" type="error" ghost @click="revoke(p)">{{ t('common.delete') }}</n-button>
        </li>
      </ul>
      <p v-else class="perms-empty">{{ t('photos.permissions.empty') }}</p>

      <div class="perms-add">
        <h4>{{ t('photos.permissions.add') }}</h4>
        <n-form>
          <n-form-item :label="t('photos.permissions.subjectType')">
            <n-select
              v-model:value="newPerm.subject_type"
              :options="[
                { label: t('photos.permissions.subjectUser'), value: 'user' },
                { label: t('photos.permissions.subjectGroup'), value: 'group' },
              ]"
            />
          </n-form-item>
          <n-form-item :label="t('photos.permissions.subjectId')">
            <n-input v-model:value="newPerm.subject_id" placeholder="keycloak-id или group-id" />
          </n-form-item>
          <n-form-item :label="t('photos.permissions.subjectName')">
            <n-input v-model:value="newPerm.subject_name" />
          </n-form-item>
          <n-form-item :label="t('photos.permissions.level')">
            <n-select
              v-model:value="newPerm.permission"
              :options="[
                { label: t('photos.permissions.perm_viewer'), value: 'viewer' },
                { label: t('photos.permissions.perm_uploader'), value: 'uploader' },
                { label: t('photos.permissions.perm_manager'), value: 'manager' },
              ]"
            />
          </n-form-item>
          <n-button type="primary" :loading="permsAdding" @click="addPerm">
            {{ t('photos.permissions.add') }}
          </n-button>
        </n-form>
      </div>
    </div>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NForm, NFormItem, NInput, NModal, NSelect, useMessage } from 'naive-ui'
import {
  fetchPermissions, grantPermission, revokePermission,
  type PhotoFolder, type PhotoFolderTreeNode, type PhotoPermission,
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
const permsAdding = ref(false)
const newPerm = ref<{
  subject_type: 'user' | 'group'
  subject_id: string
  subject_name: string
  permission: 'viewer' | 'uploader' | 'manager'
}>({ subject_type: 'user', subject_id: '', subject_name: '', permission: 'viewer' })

watch(() => [props.show, props.target] as const, async ([show, target]) => {
  if (!show || !target) return
  permsList.value = []
  newPerm.value = { subject_type: 'user', subject_id: '', subject_name: '', permission: 'viewer' }
  try {
    const r = await fetchPermissions(target.id)
    permsList.value = r.items
  } catch {
    permsList.value = []
  }
})

async function addPerm() {
  if (!props.target) return
  if (!newPerm.value.subject_id.trim() || !newPerm.value.subject_name.trim()) {
    message.warning(t('photos.permissions.fieldsRequired'))
    return
  }
  permsAdding.value = true
  try {
    const created = await grantPermission(props.target.id, { ...newPerm.value })
    permsList.value = [...permsList.value.filter(p => p.subject_id !== created.subject_id), created]
    newPerm.value.subject_id = ''
    newPerm.value.subject_name = ''
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
.perms-target { margin-bottom: 12px; }
.perms-list { list-style: none; margin: 0 0 16px; padding: 0; }
.perms-row {
  display: flex; align-items: center; justify-content: space-between;
  padding: 6px 0; border-bottom: 1px solid var(--color-border);
}
.perms-empty { color: var(--color-text-muted); font-size: 13px; margin: 0 0 16px; }
.perms-add h4 { margin: 16px 0 8px; }
</style>
