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
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NInput, NSelect, NIcon, type SelectOption } from 'naive-ui'
import { SearchOutline as SearchIcon } from '@vicons/ionicons5'

const props = defineProps<{
  searchQuery: string
  statusFilter: string | null
  tagFilter: string | null
  tagOptions: SelectOption[]
}>()

const emit = defineEmits<{
  (e: 'update:searchQuery', value: string): void
  (e: 'update:statusFilter', value: string | null): void
  (e: 'update:tagFilter', value: string | null): void
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
</style>
