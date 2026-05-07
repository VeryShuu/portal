<template>
  <div class="tree-node">
    <div class="tree-node__row">
      <button
        class="tree-node__btn"
        :class="{ 'tree-node__btn--active': activeId === section.id }"
        @click="$emit('select', section.id)"
      >
        <span v-if="section.children.length" class="tree-node__toggle" @click.stop="expanded = !expanded">
          {{ expanded ? '▾' : '▸' }}
        </span>
        <span class="tree-node__label">{{ section.title }}</span>
      </button>

      <div class="tree-node__actions">
        <button
          class="tree-node__action-btn tree-node__action-btn--add"
          :title="t('kb.add_subsection')"
          @click.stop="$emit('add-child', section.id)"
        >
          <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
            <path d="M6.5 1v11M1 6.5h11" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
          </svg>
        </button>
        <button
          class="tree-node__action-btn tree-node__action-btn--perms"
          title="Управлять доступом"
          @click.stop="$emit('manage-permissions', section.id)"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none">
            <path d="M12 2a5 5 0 0 1 5 5v1h2a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1h2V7a5 5 0 0 1 5-5zm0 11a1.5 1.5 0 1 0 0 3 1.5 1.5 0 0 0 0-3zm0-9a3 3 0 0 0-3 3v1h6V7a3 3 0 0 0-3-3z" fill="currentColor"/>
          </svg>
        </button>
        <button
          v-if="isAdmin"
          class="tree-node__action-btn tree-node__action-btn--delete"
          :title="t('kb.section.delete')"
          @click.stop="$emit('delete-section', section.id)"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none">
            <path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </button>
      </div>
    </div>
    <div v-if="expanded && section.children.length" class="tree-node__children">
      <KbSectionTree
        v-for="child in section.children"
        :key="child.id"
        :section="child"
        :active-id="activeId"
        :is-admin="isAdmin"
        @select="$emit('select', $event)"
        @add-child="$emit('add-child', $event)"
        @manage-permissions="$emit('manage-permissions', $event)"
        @delete-section="$emit('delete-section', $event)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { KbSection } from '../api/kb'

defineProps<{
  section: KbSection
  activeId: string | null
  isAdmin?: boolean
}>()

defineEmits<{
  (e: 'select', id: string): void
  (e: 'add-child', parentId: string): void
  (e: 'manage-permissions', sectionId: string): void
  (e: 'delete-section', sectionId: string): void
}>()

const { t } = useI18n()
const expanded = ref(false)
</script>

<style scoped>
.tree-node {
  margin-bottom: 2px;
}

.tree-node__row {
  display: flex;
  align-items: center;
  gap: 2px;
}

.tree-node__btn {
  display: flex;
  align-items: center;
  gap: 4px;
  flex: 1;
  text-align: left;
  padding: 7px 10px;
  border-radius: var(--radius-md);
  border: none;
  background: none;
  font-size: 14px;
  color: var(--color-text);
  cursor: pointer;
  transition: all var(--t-fast);
  font-family: inherit;
  min-width: 0;
}
.tree-node__btn:hover { background: var(--color-border); }
.tree-node__btn--active {
  background: var(--color-brand-red);
  color: #fff;
  font-weight: 600;
}

.tree-node__actions {
  display: none;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
}
.tree-node__row:hover .tree-node__actions {
  display: flex;
}

.tree-node__action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border: none;
  border-radius: var(--radius-md);
  background: none;
  cursor: pointer;
  color: var(--color-text-muted);
  transition: all var(--t-fast);
  flex-shrink: 0;
  padding: 0;
}
.tree-node__action-btn:hover {
  background: var(--color-border);
}
.tree-node__action-btn--add:hover {
  color: var(--color-brand-sky);
  background: color-mix(in srgb, var(--color-brand-sky) 12%, transparent);
}
.tree-node__action-btn--perms:hover {
  color: #7c3aed;
  background: color-mix(in srgb, #7c3aed 12%, transparent);
}
.tree-node__action-btn--delete:hover {
  color: var(--color-brand-red, #d32f2f);
  background: color-mix(in srgb, var(--color-brand-red, #d32f2f) 12%, transparent);
}

.tree-node__toggle {
  font-size: 16px;
  width: 18px;
  flex-shrink: 0;
  line-height: 1;
}

.tree-node__label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tree-node__children {
  padding-left: 18px;
}
</style>
