<template>
  <div class="staff-filters-block">
    <div
      class="staff-filters"
      :class="{ 'is-disabled': editMode }"
    >
      <div class="staff-filters__search-wrap">
        <n-input
          :value="searchInput"
          :placeholder="t('staff.searchPlaceholder')"
          clearable
          class="staff-filters__search"
          :disabled="editMode"
          @update:value="onSearchUpdate"
        >
          <template #prefix>
            <n-icon><SearchOutline /></n-icon>
          </template>
        </n-input>
        <div
          v-if="!editMode"
          class="staff-filters__hint"
        >
          {{ t('staff.searchHint') }}
        </div>
      </div>

      <n-select
        :value="departmentFilter"
        :options="departmentOptions"
        :placeholder="t('staff.filterDepartment')"
        clearable
        class="staff-filters__select"
        :disabled="editMode"
        @update:value="onDepartmentUpdate"
      />

      <n-select
        :value="officeFilter"
        :options="officeOptions"
        :placeholder="t('staff.filterOffice')"
        clearable
        class="staff-filters__select"
        :disabled="editMode"
        @update:value="onOfficeUpdate"
      />

      <n-button
        v-if="hasActiveFilters && !editMode"
        text
        @click="$emit('reset')"
      >
        {{ t('staff.resetFilters') }}
      </n-button>

      <div class="staff-filters__spacer" />

      <n-button-group
        v-if="!isMobile && !editMode"
        class="staff-view-switch"
      >
        <n-tooltip trigger="hover">
          <template #trigger>
            <n-button
              :type="view === 'table' ? 'primary' : 'default'"
              size="small"
              @click="$emit('set-view', 'table')"
            >
              <template #icon>
                <n-icon><ListOutline /></n-icon>
              </template>
            </n-button>
          </template>
          {{ t('staff.viewTable') }}
        </n-tooltip>
        <n-tooltip trigger="hover">
          <template #trigger>
            <n-button
              :type="view === 'grid' ? 'primary' : 'default'"
              size="small"
              @click="$emit('set-view', 'grid')"
            >
              <template #icon>
                <n-icon><GridOutline /></n-icon>
              </template>
            </n-button>
          </template>
          {{ t('staff.viewGrid') }}
        </n-tooltip>
      </n-button-group>

      <div class="staff-actions">
        <template v-if="editMode">
          <span
            v-if="dirty"
            class="staff-edit__unsaved"
          >
            {{ t('staff.edit.unsaved') }}
          </span>
          <n-button
            size="small"
            @click="$emit('cancel-edit')"
          >
            {{ t('staff.edit.discard') }}
          </n-button>
          <n-button
            size="small"
            type="primary"
            :loading="saving"
            :disabled="!dirty"
            @click="$emit('save-edit')"
          >
            {{ t('staff.edit.save') }}
          </n-button>
        </template>
        <template v-else>
          <n-button
            v-if="isAdmin"
            size="small"
            secondary
            @click="$emit('enter-edit')"
          >
            <template #icon>
              <n-icon><CreateOutline /></n-icon>
            </template>
            {{ t('staff.edit.enter') }}
          </n-button>
          <n-button
            size="small"
            secondary
            @click="$emit('export')"
          >
            <template #icon>
              <n-icon><DownloadOutline /></n-icon>
            </template>
            {{ t('staff.export') }}
          </n-button>
          <n-tooltip trigger="hover">
            <template #trigger>
              <n-button
                size="small"
                secondary
                @click="$emit('print')"
              >
                <template #icon>
                  <n-icon><PrintOutline /></n-icon>
                </template>
                {{ t('staff.print') }}
              </n-button>
            </template>
            {{ t('staff.printHint') }}
          </n-tooltip>
        </template>
      </div>
    </div>

    <div
      v-if="!editMode && hasActiveFilters"
      class="staff-filter-chips"
    >
      <n-tag
        v-if="searchInput"
        closable
        size="small"
        :bordered="false"
        type="info"
        @close="onClearSearch"
      >
        {{ t('staff.chips.search', { value: searchInput }) }}
      </n-tag>
      <n-tag
        v-if="departmentFilter"
        closable
        size="small"
        :bordered="false"
        type="info"
        @close="onClearDepartment"
      >
        {{ t('staff.chips.department', { value: departmentFilter }) }}
      </n-tag>
      <n-tag
        v-if="officeFilter"
        closable
        size="small"
        :bordered="false"
        type="info"
        @close="onClearOffice"
      >
        {{ t('staff.chips.office', { value: officeFilter }) }}
      </n-tag>
      <n-button
        text
        size="small"
        class="staff-filter-chips__reset"
        @click="$emit('reset')"
      >
        {{ t('staff.chips.resetAll') }}
      </n-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import {
  NButton,
  NButtonGroup,
  NIcon,
  NInput,
  NSelect,
  NTag,
  NTooltip,
} from 'naive-ui'
import type { SelectOption } from 'naive-ui'
import {
  CreateOutline,
  DownloadOutline,
  GridOutline,
  ListOutline,
  PrintOutline,
  SearchOutline,
} from '@vicons/ionicons5'

export type ViewMode = 'table' | 'grid'

defineProps<{
  searchInput: string
  departmentFilter: string | null
  officeFilter: string | null
  departmentOptions: SelectOption[]
  officeOptions: SelectOption[]
  hasActiveFilters: boolean
  view: ViewMode
  effectiveView: ViewMode
  isMobile: boolean
  isAdmin: boolean
  editMode: boolean
  dirty: boolean
  saving: boolean
}>()

const emit = defineEmits<{
  (e: 'change-search', v: string): void
  (e: 'change-department', v: string | null): void
  (e: 'change-office', v: string | null): void
  (e: 'reset'): void
  (e: 'set-view', v: ViewMode): void
  (e: 'enter-edit'): void
  (e: 'export'): void
  (e: 'print'): void
  (e: 'cancel-edit'): void
  (e: 'save-edit'): void
}>()

const { t } = useI18n()

function onSearchUpdate(v: string) {
  emit('change-search', v)
}

function onDepartmentUpdate(v: string | null) {
  emit('change-department', v)
}

function onOfficeUpdate(v: string | null) {
  emit('change-office', v)
}

function onClearSearch() {
  emit('change-search', '')
}

function onClearDepartment() {
  emit('change-department', null)
}

function onClearOffice() {
  emit('change-office', null)
}
</script>

<style scoped>
.staff-filters-block {
  position: sticky;
  top: 0;
  z-index: 5;
  background: var(--color-bg, #fff);
  padding-bottom: 6px;
}
.staff-filters {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 0 4px;
  background: var(--color-bg, #fff);
  flex-wrap: wrap;
}
.staff-filters__search-wrap {
  flex: 1 1 280px;
  max-width: 360px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.staff-filters__search { width: 100%; }
.staff-filters__hint {
  font-size: 11px;
  color: var(--color-text-muted);
  padding-left: 2px;
}
.staff-filter-chips {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  padding: 4px 0 4px;
}
.staff-filter-chips__reset { margin-left: auto; }
.staff-filters__select {
  flex: 0 1 220px;
  min-width: 160px;
}
.staff-filters__spacer { flex: 1 1 auto; }
.staff-actions {
  display: flex;
  gap: 6px;
  align-items: center;
}
.staff-edit__unsaved {
  font-size: 12px;
  color: var(--color-warning, #d97706);
  margin-right: 6px;
}

@media (max-width: 768px) {
  .staff-filters { flex-direction: column; align-items: stretch; }
  .staff-filters__search-wrap,
  .staff-filters__select { max-width: none; flex: 1 1 auto; }
}

@media print {
  .staff-filters-block,
  .staff-filters,
  .staff-filter-chips,
  .staff-view-switch,
  .staff-actions {
    display: none !important;
  }
}
</style>
