<template>
  <div class="ticket-messages">
    <div
      v-for="msg in messages"
      :key="msg.id"
      class="msg"
      :class="[msg.direction === 'outbound' ? 'msg--out' : 'msg--in', msg.visibility === 'internal' ? 'msg--internal' : '']"
    >
      <div class="msg__head">
        <span class="msg__author">
          {{ msg.author_name ?? msg.author_email }}
          <n-tag
            v-if="msg.visibility === 'internal'"
            size="tiny"
            :bordered="false"
            type="warning"
          >
            {{ t('helpdesk.internalNote') }}
          </n-tag>
        </span>
        <span class="msg__meta">
          <span
            v-if="agentMode"
            class="msg__email"
          >{{ msg.author_email }}</span>
          <span class="msg__date">{{ formatDate(msg.created_at) }}</span>
        </span>
      </div>
      <div
        v-if="msg.body_html"
        class="msg__body"
        v-html="sanitized(msg.body_html)"
      />
      <div
        v-else
        class="msg__body msg__body--plain"
      >
        {{ msg.body_text }}
      </div>
      <div
        v-if="msg.attachments?.length"
        class="msg__attachments"
      >
        <a
          v-for="att in msg.attachments"
          :key="att.id"
          :href="attachmentUrl(att.id)"
          target="_blank"
          rel="noopener"
          class="msg__attachment"
        >
          <n-icon size="18"><component :is="AttachOutline" /></n-icon>
          <span class="msg__attachment-name">{{ att.original_name }}</span>
          <span class="msg__attachment-size">{{ formatSize(att.size_bytes) }}</span>
        </a>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NTag, NIcon } from 'naive-ui'
import { AttachOutline } from '@vicons/ionicons5'
import DOMPurify from 'dompurify'
import type { HelpdeskMessage } from '../../api/helpdesk'
import { helpdeskAttachmentUrl } from '../../api/helpdesk'

defineProps<{
  messages: HelpdeskMessage[]
  /** Показывать email-адрес автора (агентский режим). */
  agentMode?: boolean
}>()

const { t, locale } = useI18n()

function sanitized(html: string): string {
  return DOMPurify.sanitize(html)
}

function attachmentUrl(id: string): string {
  return helpdeskAttachmentUrl(id)
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
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}
</script>

<style scoped>
.ticket-messages {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.msg {
  padding: 12px 16px;
  border-radius: 10px;
  border: 1px solid var(--n-border-color, rgba(0, 0, 0, 0.09));
}
.msg--out {
  background: var(--n-color-target, rgba(24, 160, 88, 0.06));
  margin-left: 32px;
}
.msg--in {
  background: var(--n-color-hover, rgba(0, 0, 0, 0.02));
  margin-right: 32px;
}
.msg--internal {
  border-style: dashed;
  background: rgba(255, 159, 27, 0.06);
}
.msg__head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  font-size: 13px;
}
.msg__author {
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 6px;
}
.msg__meta {
  display: flex;
  gap: 10px;
  color: var(--color-text-secondary);
  font-size: 12px;
}
.msg__body {
  font-size: 14px;
  line-height: 1.5;
  word-break: break-word;
}
.msg__body--plain {
  white-space: pre-wrap;
}
.msg__body :deep(img) {
  max-width: 100%;
}
.msg__attachments {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}
.msg__attachment {
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
.msg__attachment:hover {
  background: var(--n-color-hover, rgba(0, 0, 0, 0.04));
}
.msg__attachment-name {
  font-weight: 500;
  word-break: break-all;
}
.msg__attachment-size {
  color: var(--color-text-secondary, rgba(0, 0, 0, 0.45));
  font-size: 12px;
}
</style>
