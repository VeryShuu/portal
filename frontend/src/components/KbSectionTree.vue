<template>
  <div class="tree-node">
    <div
      class="tree-node__row"
      :class="{ 'tree-node__row--active': activeId === section.id }"
    >
      <span
        class="tree-node__toggle"
        :class="{ 'tree-node__toggle--leaf': !section.children.length }"
        role="button"
        tabindex="0"
        @click.stop="toggleExpand"
        @keydown.enter.stop="toggleExpand"
        @keydown.space.prevent.stop="toggleExpand"
      >
        <template v-if="section.children.length">{{ expanded ? '▾' : '▸' }}</template>
      </span>

      <button
        v-if="!renaming"
        class="tree-node__btn"
        @click="$emit('select', section.id)"
        @dblclick="canManage ? startRename() : null"
      >
        <span
          class="tree-node__label"
          :title="section.title"
        >{{ section.title }}</span>
      </button>

      <input
        v-else
        ref="renameInput"
        v-model="renameValue"
        class="tree-node__rename"
        :disabled="renameSaving"
        @click.stop
        @keydown.enter.prevent="commitRename"
        @keydown.esc.prevent="cancelRename"
        @blur="commitRename"
      >

      <span
        v-if="!renaming && menuOptions.length"
        class="tree-node__actions"
        @click.stop
      >
        <n-dropdown
          trigger="click"
          placement="bottom-end"
          :options="menuOptions"
          @select="onMenuSelect"
        >
          <button
            class="tree-node__kebab"
            :title="t('common.actions')"
            :aria-label="t('common.actions')"
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="currentColor"
              aria-hidden="true"
            >
              <circle
                cx="12"
                cy="5"
                r="1.8"
              />
              <circle
                cx="12"
                cy="12"
                r="1.8"
              />
              <circle
                cx="12"
                cy="19"
                r="1.8"
              />
            </svg>
          </button>
        </n-dropdown>
      </span>
    </div>

    <div
      v-if="expanded && section.children.length"
      class="tree-node__children"
    >
      <KbSectionTree
        v-for="child in section.children"
        :key="child.id"
        :section="child"
        :active-id="activeId"
        :is-admin="isAdmin"
        @select="$emit('select', $event)"
        @add-child="$emit('add-child', $event)"
        @rename-section="$emit('rename-section', $event)"
        @manage-permissions="$emit('manage-permissions', $event)"
        @move-section="$emit('move-section', $event)"
        @delete-section="$emit('delete-section', $event)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { NDropdown } from 'naive-ui'
import type { KbSection } from '../api/kb'
import { useKbSectionTreeExpansion } from '../composables/useKbSectionTreeExpansion'

const props = defineProps<{
  section: KbSection
  activeId: string | null
  isAdmin?: boolean
}>()

const emit = defineEmits<{
  (e: 'select', id: string): void
  (e: 'add-child', parentId: string): void
  (e: 'rename-section', payload: { id: string; title: string }): void
  (e: 'manage-permissions', sectionId: string): void
  (e: 'move-section', sectionId: string): void
  (e: 'delete-section', sectionId: string): void
}>()

const { t } = useI18n()
const expansion = useKbSectionTreeExpansion()
const expanded = computed(() => expansion.isExpanded(props.section.id))

const renaming = ref(false)
const renameSaving = ref(false)
const renameValue = ref('')
const renameInput = ref<HTMLInputElement | null>(null)

function toggleExpand() {
  if (props.section.children.length) expansion.toggle(props.section.id)
}

const perm = computed(() => props.section.user_permission ?? null)
const isAdminUser = computed(() => props.isAdmin ?? false)
const canEdit = computed(() =>
  isAdminUser.value || perm.value === 'editor' || perm.value === 'manager',
)
const canManagePerms = computed(() => isAdminUser.value || perm.value === 'manager')
const canDelete = computed(() => isAdminUser.value || perm.value === 'manager')
const canManage = computed(() => canEdit.value)

const menuOptions = computed(() => {
  const opts: Array<{ label: string; key: string; type?: string }> = []
  if (canEdit.value) {
    opts.push({ label: t('kb.add_subsection'), key: 'add-child' })
    opts.push({ label: t('kb.section.rename'), key: 'rename' })
    opts.push({ label: t('kb.section.move'), key: 'move' })
  }
  if (canManagePerms.value) {
    opts.push({ label: t('kb.permissions.title'), key: 'permissions' })
  }
  if (canDelete.value) {
    if (opts.length) opts.push({ type: 'divider', key: 'd1', label: '' })
    opts.push({ label: t('kb.section.delete'), key: 'delete' })
  }
  return opts.map((o) => o.type === 'divider' ? { type: 'divider', key: o.key } : o)
})

async function startRename() {
  if (!canManage.value) return
  renameValue.value = props.section.title
  renaming.value = true
  await nextTick()
  renameInput.value?.focus()
  renameInput.value?.select()
}

function cancelRename() {
  renaming.value = false
  renameValue.value = ''
}

function commitRename() {
  if (!renaming.value) return
  const next = renameValue.value.trim()
  if (!next || next === props.section.title) {
    cancelRename()
    return
  }
  renameSaving.value = true
  emit('rename-section', { id: props.section.id, title: next })
  // Parent handles success/failure; close immediately for snappy UX.
  renaming.value = false
  renameSaving.value = false
}

function onMenuSelect(key: string) {
  switch (key) {
    case 'add-child': emit('add-child', props.section.id); break
    case 'rename': startRename(); break
    case 'move': emit('move-section', props.section.id); break
    case 'permissions': emit('manage-permissions', props.section.id); break
    case 'delete': emit('delete-section', props.section.id); break
  }
}
</script>

<style scoped>
.tree-node {
  margin-bottom: 2px;
}

.tree-node__row {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 6px 4px 4px;
  border-radius: var(--radius-md);
  color: var(--color-text);
  transition: background var(--t-fast);
}
.tree-node__row:hover {
  background: var(--color-bg-muted, var(--color-border));
}
.tree-node__row--active,
.tree-node__row--active:hover {
  background: var(--color-brand-red);
  color: #fff;
}
.tree-node__row--active .tree-node__btn,
.tree-node__row--active .tree-node__label,
.tree-node__row--active .tree-node__kebab,
.tree-node__row--active .tree-node__toggle {
  color: #fff;
}
.tree-node__row--active .tree-node__btn {
  font-weight: 600;
}

.tree-node__toggle {
  width: 16px;
  flex-shrink: 0;
  font-size: 12px;
  line-height: 1;
  color: var(--color-text-muted);
  cursor: pointer;
  text-align: center;
  user-select: none;
}
.tree-node__toggle--leaf { cursor: default; }

.tree-node__btn {
  display: flex;
  align-items: center;
  gap: 4px;
  flex: 1;
  min-width: 0;
  text-align: left;
  padding: 6px 8px;
  border-radius: var(--radius-md);
  border: none;
  background: none;
  font-size: 14px;
  color: var(--color-text);
  cursor: pointer;
  font-family: inherit;
}
.tree-node__row--active .tree-node__btn {
  color: #fff;
}

.tree-node__rename {
  flex: 1;
  min-width: 0;
  padding: 6px 8px;
  border: 1px solid var(--color-border-strong, var(--color-border));
  border-radius: var(--radius-md);
  font-size: 14px;
  font-family: inherit;
  background: var(--color-surface);
  color: var(--color-text);
  outline: none;
}
.tree-node__rename:focus {
  border-color: var(--color-brand-red);
}

.tree-node__label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tree-node__actions {
  opacity: 0;
  flex-shrink: 0;
  transition: opacity var(--t-fast);
}
.tree-node__row:hover .tree-node__actions,
.tree-node__row--active .tree-node__actions {
  opacity: 1;
}

.tree-node__kebab {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: var(--radius-md);
  background: none;
  cursor: pointer;
  color: var(--color-text-muted);
  padding: 0;
}
.tree-node__kebab:hover {
  background: color-mix(in srgb, currentColor 12%, transparent);
  color: var(--color-text);
}
.tree-node__row--active .tree-node__kebab:hover {
  background: rgba(0, 0, 0, 0.18);
  color: #fff;
}

.tree-node__children {
  position: relative;
  padding-left: 14px;
  margin-left: 10px;
  border-left: 1px dashed var(--color-border);
}
</style>
