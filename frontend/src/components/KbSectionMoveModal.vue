<template>
  <n-modal
    :show="show"
    preset="card"
    :title="t('kb.section.moveTitle')"
    style="max-width:480px"
    @update:show="$emit('update:show', $event)"
  >
    <div
      v-if="currentSection"
      class="move-hint"
    >
      {{ t('kb.section.moveHint', { name: currentSection.title }) }}
    </div>
    <n-tree
      v-if="treeData.length"
      :data="treeData"
      :selected-keys="selectedKeys"
      :selectable="true"
      :block-line="true"
      :default-expand-all="true"
      key-field="key"
      label-field="label"
      children-field="children"
      @update:selected-keys="onSelect"
    />
    <div
      v-else
      class="move-empty"
    >
      {{ t('kb.section.moveNoTargets') }}
    </div>
    <div class="modal-actions">
      <n-button @click="$emit('update:show', false)">
        {{ t('common.cancel') }}
      </n-button>
      <n-button
        type="primary"
        :loading="saving"
        :disabled="!hasSelection"
        @click="$emit('submit', selectedParentId)"
      >
        {{ t('common.save') }}
      </n-button>
    </div>
  </n-modal>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NModal, NTree, NButton } from 'naive-ui'
import type { KbSection } from '../api/kb'

interface TreeNode {
  key: string
  label: string
  children?: TreeNode[]
  disabled?: boolean
  [k: string]: unknown
}

const props = defineProps<{
  show: boolean
  sectionId: string | null
  sections: KbSection[]
  saving: boolean
}>()

defineEmits<{
  (e: 'update:show', value: boolean): void
  (e: 'submit', parentId: string | null): void
}>()

const { t } = useI18n()

const ROOT_KEY = '__root__'

const selectedKeys = ref<string[]>([])

const hasSelection = computed(() => selectedKeys.value.length > 0)

const selectedParentId = computed<string | null>(() => {
  const k = selectedKeys.value[0]
  if (!k || k === ROOT_KEY) return null
  return k
})

function findSection(nodes: KbSection[], id: string): KbSection | null {
  for (const n of nodes) {
    if (n.id === id) return n
    const found = findSection(n.children, id)
    if (found) return found
  }
  return null
}

const currentSection = computed(() => {
  if (!props.sectionId) return null
  return findSection(props.sections, props.sectionId)
})

const currentParentId = computed<string | null>(() => {
  if (!props.sectionId) return null
  let result: string | null | undefined
  function walk(nodes: KbSection[], parentId: string | null) {
    for (const n of nodes) {
      if (n.id === props.sectionId) { result = parentId; return }
      walk(n.children, n.id)
      if (result !== undefined) return
    }
  }
  walk(props.sections, null)
  return result ?? null
})

function buildTree(nodes: KbSection[], excludeId: string | null): TreeNode[] {
  const out: TreeNode[] = []
  for (const n of nodes) {
    if (n.id === excludeId) continue
    out.push({
      key: n.id,
      label: n.title,
      children: buildTree(n.children, excludeId),
    })
  }
  return out
}

const treeData = computed<TreeNode[]>(() => {
  const filtered = buildTree(props.sections, props.sectionId)
  const rootLabel = t('kb.section.moveToRoot')
  const rootDisabled = currentParentId.value === null
  return [
    {
      key: ROOT_KEY,
      label: rootLabel + (rootDisabled ? ` (${t('kb.section.moveCurrentParent')})` : ''),
      disabled: rootDisabled,
      children: filtered,
    },
  ]
})

function onSelect(keys: string[]) {
  if (!keys.length) {
    selectedKeys.value = []
    return
  }
  const k = keys[0]
  if (k === ROOT_KEY && currentParentId.value === null) {
    return
  }
  if (k !== ROOT_KEY && currentParentId.value === k) {
    return
  }
  selectedKeys.value = [k]
}

watch(
  () => props.show,
  (v) => { if (v) selectedKeys.value = [] },
)
</script>

<style scoped>
.move-hint {
  font-size: 13px;
  color: var(--color-text-muted);
  margin-bottom: 12px;
}
.move-empty {
  padding: 16px 0;
  text-align: center;
  color: var(--color-text-muted);
  font-size: 13px;
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 16px;
}
</style>
