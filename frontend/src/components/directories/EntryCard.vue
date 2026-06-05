<template>
  <div class="entry-card">
    <div class="entry-card__head">
      <div class="entry-card__main">
        <div
          class="entry-card__name"
          v-html="hl ? hl(entry.name) : entry.name"
        />
      </div>
      <div
        v-if="canEdit"
        class="entry-card__actions"
      >
        <span
          v-if="draggable"
          class="entry-card__drag drag-handle"
          :title="t('directories.dragHint')"
        >
          <n-icon><ReorderThreeOutline /></n-icon>
        </span>
        <n-button
          quaternary
          circle
          size="small"
          class="entry-card__edit"
          :title="t('common.edit')"
          @click.stop="$emit('edit', entry)"
        >
          <template #icon>
            <n-icon><CreateOutline /></n-icon>
          </template>
        </n-button>
      </div>
    </div>

    <ul
      v-if="fieldRows.length"
      class="entry-card__fields"
    >
      <li
        v-for="f in fieldRows"
        :key="f.key"
        class="entry-card__field"
      >
        <span class="entry-card__field-label">{{ f.label }}</span>
        <span
          class="entry-card__field-value"
          :class="{ 'is-code': isCodeValue(f.value) }"
        >{{ f.value }}</span>
      </li>
    </ul>

    <EntryContactList
      v-if="entry.contacts.length"
      :contacts="entry.contacts"
      :channels="directory.channels"
      :lang="lang"
      :class="{ 'entry-card__contacts--divided': fieldRows.length }"
    />

    <div
      v-if="entry.note"
      class="entry-card__note"
    >
      {{ entry.note }}
    </div>

    <router-link
      v-if="entry.folder_id"
      class="entry-card__folder"
      :to="{ path: '/files', query: { folder: entry.folder_id } }"
      @click.stop
    >
      <n-icon :size="14">
        <DocumentsOutline />
      </n-icon>
      {{ t('directories.filesLink') }}
    </router-link>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NIcon } from 'naive-ui'
import { CreateOutline, DocumentsOutline, ReorderThreeOutline } from '@vicons/ionicons5'
import type { DirectoryPublic, EntryPublic } from '../../api/directories'
import EntryContactList from './EntryContactList.vue'

const props = defineProps<{
  entry: EntryPublic
  directory: DirectoryPublic
  canEdit?: boolean
  draggable?: boolean
  hl?: (text: string | null | undefined) => string
  lang?: 'ru' | 'en'
}>()

defineEmits<{
  (e: 'edit', entry: EntryPublic): void
}>()

const { t } = useI18n()

function isCodeValue(value: string): boolean {
  return /\p{N}/u.test(value) && !/[\p{L}@]/u.test(value)
}

const fieldRows = computed(() => {
  const fields = [...props.directory.field_schema].sort((a, b) => a.sort_order - b.sort_order)
  return fields
    .map((f) => ({
      key: f.key,
      label: props.lang === 'en' && f.label_en ? f.label_en : f.label_ru,
      value: props.entry.attributes[f.key] ?? '',
    }))
    .filter((r) => r.value)
})
</script>

<style scoped>
.entry-card {
  --dir-label-col: 132px;
  --dir-label-color: color-mix(in srgb, var(--color-text-muted) 70%, var(--color-text));
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px;
  border-radius: 10px;
  background: var(--color-surface, #fff);
  border: 1px solid var(--n-border-color, rgba(0, 0, 0, 0.08));
  height: 100%;
}
.entry-card__head {
  display: flex;
  gap: 12px;
  align-items: center;
}
.entry-card__main {
  min-width: 0;
  flex: 1;
}
.entry-card__name {
  font-weight: 600;
  font-size: 15px;
  color: var(--color-text);
  line-height: 1.2;
}
.entry-card__folder {
  display: inline-flex;
  align-self: flex-start;
  align-items: center;
  gap: 5px;
  margin-top: auto;
  padding-top: 8px;
  border-top: 1px dashed var(--n-border-color, rgba(0, 0, 0, 0.08));
  width: 100%;
  font-size: 12.5px;
  font-weight: 500;
  color: var(--color-brand-navy, #1f3a5f);
  text-decoration: none;
}
.entry-card__folder:hover {
  text-decoration: underline;
}
.entry-card__actions {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 2px;
}
.entry-card__edit {
  flex: 0 0 auto;
}
.entry-card__drag {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  color: var(--color-text-muted);
  cursor: grab;
  touch-action: none;
}
.entry-card__drag:active {
  cursor: grabbing;
}
.entry-card__fields {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
}
.entry-card__field {
  display: flex;
  gap: 8px;
  align-items: baseline;
}
.entry-card__field-label {
  flex: 0 0 var(--dir-label-col);
  font-weight: 500;
  color: var(--dir-label-color, var(--color-text-muted));
}
.entry-card__field-value {
  min-width: 0;
  color: var(--color-text);
  word-break: break-word;
}
.entry-card__field-value.is-code {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-variant-numeric: tabular-nums;
}
.entry-card__contacts--divided {
  padding-top: 10px;
  border-top: 1px solid var(--n-border-color, rgba(0, 0, 0, 0.08));
}
.entry-card__note {
  padding-top: 8px;
  border-top: 1px dashed var(--n-border-color, rgba(0, 0, 0, 0.08));
  font-size: 12.5px;
  color: var(--color-text-muted);
  white-space: pre-wrap;
}
</style>
