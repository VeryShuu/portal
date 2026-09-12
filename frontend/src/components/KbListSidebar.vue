<template>
  <aside class="kb-sidebar">
    <div class="kb-sidebar__header">
      <div class="kb-sidebar__title">
        {{ t('kb.sections') }}
      </div>
    </div>
    <button
      class="sidebar-add-btn"
      :title="t('kb.create_root_section')"
      @click="sectionsCtl.openCreateSection(null)"
    >
      <svg
        width="14"
        height="14"
        viewBox="0 0 13 13"
        fill="none"
        aria-hidden="true"
      >
        <path
          d="M6.5 1v11M1 6.5h11"
          stroke="currentColor"
          stroke-width="1.8"
          stroke-linecap="round"
        />
      </svg>
      <span>{{ t('kb.new_section') }}</span>
    </button>
    <div
      v-if="sectionsCtl.sectionsLoading.value"
      class="kb-sidebar__loading"
    >
      <SkeletonCard
        v-for="i in 6"
        :key="i"
        variant="folder-item"
      />
    </div>
    <div
      v-else
      class="kb-tree"
    >
      <button
        class="kb-tree__item"
        :class="{ 'kb-tree__item--active': !sectionsCtl.selectedSection.value }"
        @click="emit('select-section', null)"
      >
        {{ t('kb.allArticles') }}
      </button>
      <KbSectionTree
        v-for="section in sectionsCtl.sections.value"
        :key="section.id"
        :section="section"
        :active-id="sectionsCtl.selectedSection.value"
        :is-admin="isAdmin"
        @select="emit('select-section', $event)"
        @add-child="sectionsCtl.openCreateSection"
        @rename-section="sectionsCtl.renameSection"
        @manage-permissions="sectionsCtl.openSectionPermissions"
        @move-section="sectionsCtl.openMoveSection"
        @delete-section="sectionsCtl.confirmDeleteSection"
      />
    </div>
  </aside>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import SkeletonCard from './SkeletonCard.vue'
import KbSectionTree from './KbSectionTree.vue'
import type { useKbSections } from '../composables/useKbSections'

defineProps<{
  sectionsCtl: ReturnType<typeof useKbSections>
  isAdmin: boolean
}>()

const emit = defineEmits<{
  (e: 'select-section', id: string | null): void
}>()

const { t } = useI18n()
</script>

<style scoped>
.kb-sidebar {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 16px;
  position: sticky;
  top: 80px;
}
.kb-sidebar__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
  gap: 8px;
}

.kb-sidebar__title {
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--color-text-muted);
}

.sidebar-add-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: 100%;
  min-height: 38px;
  padding: 8px 12px;
  margin-bottom: 14px;
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-md);
  background: none;
  color: var(--color-text-muted);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--t-fast);
  font-family: inherit;
  white-space: nowrap;
}
.sidebar-add-btn:hover {
  border-color: var(--color-brand-red);
  background: color-mix(in srgb, var(--color-brand-red) 8%, transparent);
  color: var(--color-brand-red);
}

.kb-tree__item {
  display: block;
  width: 100%;
  text-align: left;
  padding: 9px 12px;
  min-height: 36px;
  border-radius: var(--radius-md);
  border: none;
  background: none;
  font-size: 14px;
  color: var(--color-text);
  cursor: pointer;
  transition: all var(--t-fast);
  font-family: inherit;
}
.kb-tree__item:hover { background: var(--color-border); }
.kb-tree__item--active {
  background: var(--color-brand-red);
  color: #fff;
  font-weight: 600;
}
</style>
