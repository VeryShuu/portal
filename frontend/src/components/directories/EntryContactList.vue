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
          <span
            class="contact-row__value"
            :class="{ 'is-code': isCodeValue(c.value) }"
          >{{ c.value }}</span>
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

function isCodeValue(value: string): boolean {
  return /\p{N}/u.test(value) && !/[\p{L}@]/u.test(value)
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
  gap: 12px;
}
.contact-group + .contact-group {
  padding-top: 12px;
  border-top: 1px solid var(--n-border-color, rgba(0, 0, 0, 0.06));
}
.contact-group__role {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--dir-label-color, var(--color-text-muted));
  margin-bottom: 4px;
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
  align-items: flex-start;
  gap: 8px;
  font-size: 13px;
  min-width: 0;
}
.contact-row__channel {
  flex: 0 0 var(--dir-label-col, 96px);
  color: var(--dir-label-color, var(--color-text-muted));
}
.contact-row__value {
  flex: 1 1 auto;
  min-width: 0;
  color: var(--color-text);
  overflow-wrap: anywhere;
}
.contact-row__value.is-code {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-variant-numeric: tabular-nums;
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
