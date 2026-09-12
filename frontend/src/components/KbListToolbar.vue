<template>
  <div class="kb-toolbar">
    <n-input
      :value="searchQuery"
      :placeholder="t('kb.searchPlaceholder')"
      clearable
      size="medium"
      style="flex:1;max-width:400px"
      @update:value="onSearchUpdate"
    >
      <template #prefix>
        <n-icon><SearchIcon /></n-icon>
      </template>
    </n-input>

    <n-select
      :value="statusFilter"
      :options="statusOptions"
      size="medium"
      clearable
      :placeholder="t('kb.filterStatus')"
      style="width:160px"
      @update:value="$emit('update:statusFilter', $event)"
    />

    <n-select
      v-if="tagOptions.length"
      :value="tagFilter"
      :options="tagOptions"
      size="medium"
      clearable
      :placeholder="t('kb.filterTag')"
      style="width:160px"
      @update:value="$emit('update:tagFilter', $event)"
    />

    <div
      v-if="viewMode !== undefined"
      class="kb-view-toggle"
      role="group"
      :aria-label="t('kb.viewMode')"
    >
      <button
        type="button"
        class="kb-view-toggle__btn"
        :class="{ 'kb-view-toggle__btn--active': viewMode === 'list' }"
        :title="t('kb.viewList')"
        :aria-pressed="viewMode === 'list'"
        @click="$emit('update:viewMode', 'list')"
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          aria-hidden="true"
        >
          <line
            x1="8"
            y1="6"
            x2="20"
            y2="6"
          />
          <line
            x1="8"
            y1="12"
            x2="20"
            y2="12"
          />
          <line
            x1="8"
            y1="18"
            x2="20"
            y2="18"
          />
          <circle
            cx="4"
            cy="6"
            r="1"
          />
          <circle
            cx="4"
            cy="12"
            r="1"
          />
          <circle
            cx="4"
            cy="18"
            r="1"
          />
        </svg>
      </button>
      <button
        type="button"
        class="kb-view-toggle__btn"
        :class="{ 'kb-view-toggle__btn--active': viewMode === 'grid' }"
        :title="t('kb.viewGrid')"
        :aria-pressed="viewMode === 'grid'"
        @click="$emit('update:viewMode', 'grid')"
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          aria-hidden="true"
        >
          <rect
            x="3"
            y="3"
            width="8"
            height="8"
            rx="1.5"
          />
          <rect
            x="13"
            y="3"
            width="8"
            height="8"
            rx="1.5"
          />
          <rect
            x="3"
            y="13"
            width="8"
            height="8"
            rx="1.5"
          />
          <rect
            x="13"
            y="13"
            width="8"
            height="8"
            rx="1.5"
          />
        </svg>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NInput, NSelect, NIcon, type SelectOption } from 'naive-ui'
import { SearchOutline as SearchIcon } from '@vicons/ionicons5'

export type KbViewMode = 'list' | 'grid'

const props = defineProps<{
  searchQuery: string
  statusFilter: string | null
  tagFilter: string | null
  tagOptions: SelectOption[]
  viewMode?: KbViewMode
}>()

const emit = defineEmits<{
  (e: 'update:searchQuery', value: string): void
  (e: 'update:statusFilter', value: string | null): void
  (e: 'update:tagFilter', value: string | null): void
  (e: 'update:viewMode', value: KbViewMode): void
  (e: 'search-input'): void
}>()

void props

const { t } = useI18n()

const statusOptions = computed(() => [
  { label: t('kb.status.draft'), value: 'draft' },
  { label: t('kb.status.published'), value: 'published' },
  { label: t('kb.status.archived'), value: 'archived' },
])

function onSearchUpdate(value: string) {
  emit('update:searchQuery', value)
  emit('search-input')
}
</script>

<style scoped>
.kb-toolbar {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.kb-view-toggle {
  display: inline-flex;
  margin-left: auto;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  overflow: hidden;
  background: var(--color-surface);
}
.kb-view-toggle__btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  background: none;
  border: none;
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all var(--t-fast);
}
.kb-view-toggle__btn:hover {
  color: var(--color-text);
  background: var(--color-bg-muted, var(--color-border));
}
.kb-view-toggle__btn--active {
  background: var(--color-brand-red);
  color: #fff;
}
.kb-view-toggle__btn--active:hover {
  background: var(--color-brand-red);
  color: #fff;
}
</style>
