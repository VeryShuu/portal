<template>
  <div class="contact-list">
    <div
      v-for="group in groups"
      :key="group.role"
      class="contact-group"
    >
      <div
        v-if="group.role"
        class="contact-group__role"
      >
        {{ group.role }}
      </div>
      <ul class="contact-group__items">
        <li
          v-for="c in group.contacts"
          :key="c.id"
          class="contact-row"
        >
          <span class="contact-row__channel">{{ channelLabel(c.channel) }}</span>
          <span class="contact-row__value">{{ c.value }}</span>
          <span
            v-if="c.label"
            class="contact-row__label"
          >{{ c.label }}</span>
          <button
            class="copy-btn"
            type="button"
            :title="t('directories.copy')"
            @click="copyValue(c.value)"
          >
            <n-icon :size="13">
              <CopyOutline />
            </n-icon>
          </button>
        </li>
      </ul>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NIcon, useMessage } from 'naive-ui'
import { CopyOutline } from '@vicons/ionicons5'
import type { ContactPublic, DirectoryChannel } from '../../api/directories'

const props = defineProps<{
  contacts: ContactPublic[]
  channels: DirectoryChannel[]
  lang?: 'ru' | 'en'
}>()

const { t } = useI18n()
const message = useMessage()

const channelMap = computed(() => {
  const m = new Map<string, DirectoryChannel>()
  for (const c of props.channels) m.set(c.key, c)
  return m
})

function channelLabel(key: string): string {
  const c = channelMap.value.get(key)
  if (!c) return key
  return props.lang === 'en' && c.label_en ? c.label_en : c.label_ru
}

const groups = computed(() => {
  const sorted = [...props.contacts].sort((a, b) => a.sort_order - b.sort_order)
  const map = new Map<string, { role: string; contacts: ContactPublic[] }>()
  for (const c of sorted) {
    const role = c.role ?? ''
    if (!map.has(role)) map.set(role, { role, contacts: [] })
    map.get(role)!.contacts.push(c)
  }
  return Array.from(map.values())
})

async function copyValue(value: string) {
  try {
    await navigator.clipboard.writeText(value)
    message.success(t('directories.copied'))
  } catch {
    message.error(t('directories.copyFailed'))
  }
}
</script>

<style scoped>
.contact-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.contact-group__role {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-muted);
  margin-bottom: 2px;
}
.contact-group__items {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.contact-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  min-width: 0;
}
.contact-row__channel {
  flex: 0 0 auto;
  color: var(--color-text-muted);
  min-width: 96px;
}
.contact-row__value {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.contact-row__label {
  color: var(--color-text-muted);
  font-size: 12px;
}
.copy-btn {
  margin-left: auto;
  padding: 2px 4px;
  border: none;
  background: transparent;
  color: var(--color-text-muted);
  cursor: pointer;
  border-radius: 4px;
  opacity: 0;
  transition: opacity 0.15s ease, background-color 0.15s ease;
}
.contact-row:hover .copy-btn,
.copy-btn:focus-visible {
  opacity: 1;
}
.copy-btn:hover {
  background: var(--n-merged-color-hover, rgba(0, 0, 0, 0.06));
  color: var(--color-text);
}
@media (hover: none) {
  .copy-btn { opacity: 1; }
}
</style>
