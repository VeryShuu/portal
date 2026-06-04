<template>
  <div class="entry-card">
    <div class="entry-card__head">
      <n-avatar
        :size="48"
        :src="entry.avatar_path ?? undefined"
        class="entry-card__avatar"
      >
        {{ initials }}
      </n-avatar>
      <div class="entry-card__main">
        <div
          class="entry-card__name"
          v-html="hl ? hl(entry.name) : entry.name"
        />
        <a
          v-if="entry.folder_url"
          class="entry-card__folder"
          :href="entry.folder_url"
          target="_blank"
          rel="noopener"
          @click.stop
        >
          <n-icon :size="13">
            <FolderOpenOutline />
          </n-icon>
          {{ t('directories.openFolder') }}
        </a>
      </div>
      <n-button
        v-if="canEdit"
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

    <ul
      v-if="fieldRows.length"
      class="entry-card__fields"
    >
      <li
        v-for="f in fieldRows"
        :key="f.key"
      >
        <span class="entry-card__field-label">{{ f.label }}:</span>
        <span class="entry-card__field-value">{{ f.value }}</span>
      </li>
    </ul>

    <EntryContactList
      v-if="entry.contacts.length"
      :contacts="entry.contacts"
      :channels="directory.channels"
      :lang="lang"
    />

    <div
      v-if="entry.note"
      class="entry-card__note"
    >
      {{ entry.note }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NAvatar, NButton, NIcon } from 'naive-ui'
import { CreateOutline, FolderOpenOutline } from '@vicons/ionicons5'
import type { DirectoryPublic, EntryPublic } from '../../api/directories'
import EntryContactList from './EntryContactList.vue'

const props = defineProps<{
  entry: EntryPublic
  directory: DirectoryPublic
  canEdit?: boolean
  hl?: (text: string | null | undefined) => string
  lang?: 'ru' | 'en'
}>()

defineEmits<{
  (e: 'edit', entry: EntryPublic): void
}>()

const { t } = useI18n()

const initials = computed(() => {
  const name = props.entry.name?.trim() ?? ''
  if (!name) return '?'
  const parts = name.split(/\s+/).filter(Boolean)
  const a = parts[0]?.[0] ?? ''
  const b = parts[1]?.[0] ?? ''
  return (a + b).toUpperCase() || '?'
})

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
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px;
  border-radius: 10px;
  background: var(--color-surface, #fff);
  border: 1px solid var(--n-border-color, rgba(0, 0, 0, 0.08));
}
.entry-card__head {
  display: flex;
  gap: 12px;
  align-items: center;
}
.entry-card__avatar {
  flex: 0 0 auto;
  background: var(--color-brand-navy, #1f3a5f);
  color: #fff;
  font-weight: 600;
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
  align-items: center;
  gap: 4px;
  margin-top: 4px;
  font-size: 12.5px;
  color: var(--color-brand-navy, #1f3a5f);
  text-decoration: none;
}
.entry-card__folder:hover {
  text-decoration: underline;
}
.entry-card__edit {
  flex: 0 0 auto;
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
.entry-card__field-label {
  font-weight: 500;
  color: var(--color-text-muted);
  margin-right: 6px;
}
.entry-card__field-value {
  color: var(--color-text);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
.entry-card__note {
  padding-top: 8px;
  border-top: 1px dashed var(--n-border-color, rgba(0, 0, 0, 0.08));
  font-size: 12.5px;
  color: var(--color-text-muted);
  white-space: pre-wrap;
}
</style>
