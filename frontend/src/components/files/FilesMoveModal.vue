<template>
  <n-modal
    :show="show"
    :title="t('files.bulk.moveTitle')"
    preset="card"
    style="width: 520px"
    @update:show="$emit('update:show', $event)"
  >
    <n-tree
      v-if="treeData.length"
      :data="treeData"
      :selected-keys="targetKey ? [targetKey] : []"
      :default-expand-all="true"
      block-line
      selectable
      @update:selected-keys="onSelect"
    />
    <p
      v-else
      class="files-move-empty"
    >
      {{ t('files.bulk.noEditableTargets') }}
    </p>
    <template #footer>
      <div style="display: flex; gap: 8px; justify-content: flex-end">
        <n-button @click="$emit('update:show', false)">
          {{ t('common.cancel') }}
        </n-button>
        <n-button
          type="primary"
          :loading="loading"
          :disabled="!targetKey || loading"
          @click="$emit('confirm')"
        >
          {{ t('files.bulk.moveConfirm') }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NButton, NModal, NTree, type TreeOption } from 'naive-ui'

defineProps<{
  show: boolean
  treeData: TreeOption[]
  targetKey: string | null
  loading: boolean
}>()

const emit = defineEmits<{
  'update:show': [value: boolean]
  'update:targetKey': [value: string | null]
  confirm: []
}>()

const { t } = useI18n()

function onSelect(keys: Array<string | number>) {
  emit('update:targetKey', keys.length ? String(keys[0]) : null)
}
</script>

<style scoped>
.files-move-empty {
  color: var(--n-text-color-3, #999);
  font-size: 13px;
}
</style>
