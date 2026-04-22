<template>
  <div class="tree-node">
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
    <div v-if="expanded && section.children.length" class="tree-node__children">
      <KbSectionTree
        v-for="child in section.children"
        :key="child.id"
        :section="child"
        :active-id="activeId"
        @select="$emit('select', $event)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { KbSection } from '../api/kb'

defineProps<{
  section: KbSection
  activeId: string | null
}>()

defineEmits<{
  (e: 'select', id: string): void
}>()

const expanded = ref(false)
</script>

<style scoped>
.tree-node {
  margin-bottom: 2px;
}

.tree-node__btn {
  display: flex;
  align-items: center;
  gap: 4px;
  width: 100%;
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
}

.tree-node__btn:hover { background: var(--color-border); }
.tree-node__btn--active {
  background: var(--color-brand-red);
  color: #fff;
  font-weight: 600;
}

.tree-node__toggle {
  font-size: 11px;
  width: 14px;
  flex-shrink: 0;
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
