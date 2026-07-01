<template>
  <div class="ticket-chat">
    <div
      v-for="msg in messages"
      :key="msg.id"
      class="chat-row"
      :class="rowClass(msg)"
    >
      <n-avatar
        round
        :size="34"
        class="chat-row__avatar"
        :style="{ background: avatarColor(msg) }"
      >
        {{ initials(msg) }}
      </n-avatar>
      <div
        class="chat-bubble"
        :class="bubbleClass(msg)"
      >
        <div class="chat-bubble__head">
          <span class="chat-bubble__author">{{ authorLabel(msg) }}</span>
          <n-tag
            v-if="msg.visibility === 'internal'"
            size="tiny"
            :bordered="false"
            type="warning"
            class="chat-bubble__note"
          >
            {{ t('helpdesk.internalNote') }}
          </n-tag>
          <n-tag
            v-if="msg.source === 'email'"
            size="tiny"
            :bordered="false"
            class="chat-bubble__src"
          >
            {{ t('helpdesk.sources.email') }}
          </n-tag>
          <span class="chat-bubble__meta">
            <span
              v-if="agentMode"
              class="chat-bubble__email"
            >{{ msg.author_email }}</span>
            <span class="chat-bubble__date">{{ formatDate(msg.created_at) }}</span>
          </span>
        </div>
        <div
          v-if="msg.body_html"
          class="chat-bubble__body"
          v-html="sanitized(msg.body_html)"
        />
        <div
          v-else
          class="chat-bubble__body chat-bubble__body--plain"
        >
          {{ msg.body_text }}
        </div>
        <div
          v-if="msg.attachments?.length"
          class="chat-bubble__attachments"
        >
          <a
            v-for="att in msg.attachments"
            :key="att.id"
            :href="attachmentUrl(att.id)"
            target="_blank"
            rel="noopener"
            class="chat-bubble__attachment"
          >
            <n-icon size="18"><component :is="AttachOutline" /></n-icon>
            <span class="chat-bubble__attachment-name">{{ att.original_name }}</span>
            <span class="chat-bubble__attachment-size">{{ formatSize(att.size_bytes) }}</span>
          </a>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NTag, NIcon, NAvatar } from 'naive-ui'
import { AttachOutline } from '@vicons/ionicons5'
import type { HelpdeskMessage } from '../../api/helpdesk'
import { helpdeskAttachmentUrl } from '../../api/helpdesk'
import { sanitizeHtml } from '../../utils/sanitize'

defineProps<{
  messages: HelpdeskMessage[]
  /** Показывать email-адрес автора (агентский режим). */
  agentMode?: boolean
}>()

const { t, locale } = useI18n()

function sanitized(html: string): string {
  return sanitizeHtml(html)
}

function attachmentUrl(id: string): string {
  return helpdeskAttachmentUrl(id)
}

function isOut(msg: HelpdeskMessage): boolean {
  return msg.direction === 'outbound'
}

function rowClass(msg: HelpdeskMessage): string {
  return isOut(msg) ? 'chat-row--out' : 'chat-row--in'
}

function bubbleClass(msg: HelpdeskMessage): string {
  const cls: string[] = []
  if (isOut(msg)) cls.push('chat-bubble--out')
  else cls.push('chat-bubble--in')
  if (msg.visibility === 'internal') cls.push('chat-bubble--internal')
  return cls.join(' ')
}

function authorLabel(msg: HelpdeskMessage): string {
  return msg.author_name ?? msg.author_email
}

function initials(msg: HelpdeskMessage): string {
  const name = (msg.author_name ?? msg.author_email ?? '').trim()
  if (!name) return '?'
  // Для email берём первый символ local-part (до @).
  const source = name.includes('@') ? name.split('@')[0] : name
  const parts = source.split(/[\s._-]+/).filter(Boolean)
  const a = parts[0]?.[0] ?? ''
  const b = parts[1]?.[0] ?? ''
  return (a + b).toUpperCase() || '?'
}

// Палитра цветов аватаров (детерминированно из email) — как в мессенджерах.
const AVATAR_COLORS = [
  '#2080f0',
  '#18a058',
  '#f0a020',
  '#d03050',
  '#8a2be2',
  '#0ea5e9',
  '#ea580c',
  '#64748b',
]

function avatarColor(msg: HelpdeskMessage): string {
  const key = (msg.author_email || msg.author_name || '?').toLowerCase()
  let hash = 0
  for (let i = 0; i < key.length; i++) {
    hash = (hash * 31 + key.charCodeAt(i)) >>> 0
  }
  return AVATAR_COLORS[hash % AVATAR_COLORS.length]
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString(locale.value === 'ru' ? 'ru-RU' : 'en-US', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}
</script>

<style scoped>
.ticket-chat {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.chat-row {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}
.chat-row--in {
  flex-direction: row;
}
.chat-row--out {
  flex-direction: row-reverse;
}
.chat-row__avatar {
  flex: 0 0 auto;
  color: #fff;
  font-size: 13px;
  font-weight: 600;
}
.chat-bubble {
  max-width: 75%;
  padding: 10px 14px;
  border-radius: 14px;
  border: 1px solid var(--n-border-color, rgba(0, 0, 0, 0.09));
  word-break: break-word;
}
.chat-bubble--in {
  background: var(--n-color-hover, rgba(0, 0, 0, 0.02));
  border-top-left-radius: 4px;
}
.chat-bubble--out {
  background: var(--n-color-target, rgba(24, 160, 88, 0.08));
  border-top-right-radius: 4px;
}
.chat-bubble--internal {
  border-style: dashed;
  background: rgba(255, 159, 27, 0.08);
  border-color: rgba(255, 159, 27, 0.4);
}
.chat-bubble__head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
  font-size: 13px;
  flex-wrap: wrap;
}
.chat-row--out .chat-bubble__head {
  flex-direction: row-reverse;
}
.chat-bubble__author {
  font-weight: 600;
}
.chat-bubble__note,
.chat-bubble__src {
  flex: 0 0 auto;
}
.chat-bubble__meta {
  display: flex;
  gap: 10px;
  color: var(--color-text-secondary);
  font-size: 12px;
}
.chat-bubble__email {
  font-style: italic;
}
.chat-bubble__body {
  font-size: 14px;
  line-height: 1.5;
}
.chat-bubble__body--plain {
  white-space: pre-wrap;
}
.chat-bubble__body :deep(img) {
  max-width: 100%;
}
.chat-bubble__attachments {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}
.chat-bubble__attachment {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border: 1px solid var(--n-border-color, rgba(0, 0, 0, 0.12));
  border-radius: 8px;
  font-size: 13px;
  color: var(--color-text-primary, inherit);
  text-decoration: none;
  transition: background 0.15s ease;
}
.chat-bubble__attachment:hover {
  background: var(--n-color-hover, rgba(0, 0, 0, 0.04));
}
.chat-bubble__attachment-name {
  font-weight: 500;
  word-break: break-all;
}
.chat-bubble__attachment-size {
  color: var(--color-text-secondary, rgba(0, 0, 0, 0.45));
  font-size: 12px;
}
</style>
