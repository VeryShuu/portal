<template>
  <div
    ref="rootEl"
    class="staff-edit"
  >
    <div
      v-for="(group, gIdx) in editGroups"
      :key="group.department"
      class="staff-edit__group"
      :data-dept-key="group.department"
    >
      <div class="staff-edit__group-header">
        <span
          class="drag-handle drag-handle--dept"
          :title="t('staff.edit.dragDept')"
        >
          <n-icon><ReorderThreeOutline /></n-icon>
        </span>
        <span class="staff-edit__group-name">
          {{ group.department || '—' }}
        </span>
        <span class="staff-edit__group-count">{{ group.users.length }}</span>
      </div>
      <ul
        class="staff-edit__user-list"
        :data-dept-idx="gIdx"
      >
        <li
          v-for="user in group.users"
          :key="user.id"
          :data-user-id="user.id"
          class="staff-edit__user"
          :class="{ 'is-hidden': user.staff_hidden }"
        >
          <span
            class="drag-handle drag-handle--user"
            :title="t('staff.edit.dragUser')"
          >
            <n-icon><ReorderTwoOutline /></n-icon>
          </span>
          <div class="staff-edit__user-main">
            <div class="staff-edit__user-name">
              {{ user.full_name }}
            </div>
            <div class="staff-edit__user-pos">
              {{ user.position || '—' }}
            </div>
          </div>
          <span
            v-if="user.staff_hidden"
            class="staff-edit__hidden-badge"
          >
            {{ t('staff.edit.hiddenBadge') }}
          </span>
          <n-button
            size="small"
            quaternary
            circle
            :title="user.staff_hidden ? t('staff.edit.show') : t('staff.edit.hide')"
            @click="$emit('toggle-user-hidden', user.id)"
          >
            <template #icon>
              <n-icon>
                <EyeOffOutline v-if="user.staff_hidden" />
                <EyeOutline v-else />
              </n-icon>
            </template>
          </n-button>
        </li>
      </ul>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NIcon } from 'naive-ui'
import {
  EyeOffOutline,
  EyeOutline,
  ReorderThreeOutline,
  ReorderTwoOutline,
} from '@vicons/ionicons5'
import type { StaffEditGroup } from '../../composables/useStaffEdit'

defineProps<{
  editGroups: StaffEditGroup[]
}>()

const emit = defineEmits<{
  (e: 'toggle-user-hidden', userId: string): void
  (e: 'root-ready', el: HTMLElement | null): void
}>()

const { t } = useI18n()
const rootEl = ref<HTMLElement | null>(null)

watch(rootEl, (el) => emit('root-ready', el))

onMounted(() => {
  emit('root-ready', rootEl.value)
})

onBeforeUnmount(() => {
  emit('root-ready', null)
})
</script>

<style scoped>
.staff-edit {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.staff-edit__group {
  border: 1px solid var(--n-border-color, rgba(0, 0, 0, 0.1));
  border-radius: 8px;
  background: var(--color-surface, #fafafa);
}
.staff-edit__group-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--n-border-color, rgba(0, 0, 0, 0.08));
  background: var(--color-bg, #fff);
  border-top-left-radius: 8px;
  border-top-right-radius: 8px;
}
.staff-edit__group-name {
  font-weight: 600;
  font-size: 14px;
  color: var(--color-text);
  flex: 1;
}
.staff-edit__group-count {
  font-size: 12px;
  color: var(--color-text-muted);
}
.staff-edit__user-list {
  list-style: none;
  margin: 0;
  padding: 6px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-height: 8px;
}
.staff-edit__user {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  background: var(--color-bg, #fff);
  border: 1px solid var(--n-border-color, rgba(0, 0, 0, 0.08));
  border-radius: 6px;
}
.staff-edit__user.is-hidden {
  opacity: 0.55;
  background: var(--color-surface, #fafafa);
}
.staff-edit__user-main {
  flex: 1;
  min-width: 0;
}
.staff-edit__user-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.staff-edit__user-pos {
  font-size: 12px;
  color: var(--color-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.staff-edit__hidden-badge {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 999px;
  background: var(--color-bg-muted, rgba(0, 0, 0, 0.06));
  color: var(--color-text-muted);
}
.drag-handle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-muted);
  cursor: grab;
  padding: 4px;
  border-radius: 4px;
}
.drag-handle:active { cursor: grabbing; }
.drag-handle:hover {
  background: var(--color-bg-muted, rgba(0, 0, 0, 0.06));
  color: var(--color-text);
}
.sortable-ghost {
  opacity: 0.6;
  background: var(--n-color-target, rgba(99, 102, 241, 0.04)) !important;
  border: 1px dashed var(--n-color-primary, #2080f0) !important;
  border-radius: 8px;
}
.sortable-chosen {
  transform: translateY(-1px);
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.16);
  cursor: grabbing;
}
.sortable-drag {
  cursor: grabbing;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.18);
}

.staff-edit.is-dragging-dept .staff-edit__user-list {
  display: none;
}
.staff-edit.is-dragging-dept .staff-edit__group {
  background: var(--color-surface, #fafafa);
}
.staff-edit.is-dragging-dept .staff-edit__group-header {
  border-bottom: none;
  border-radius: 8px;
}

</style>
