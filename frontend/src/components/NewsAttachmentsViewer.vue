<template>
  <div class="attachments" v-if="attachments.length">
    <h3 class="attachments__title">{{ t('news.attachments.title') }}</h3>
    <div class="attachments__list">
      <a
        v-for="att in attachments"
        :key="att.id"
        :href="att.download_url"
        class="attachment-item"
        download
        target="_blank"
        rel="noopener noreferrer"
      >
        <div class="attachment-item__icon">
          <n-icon size="22" :color="iconColor(att.mime_type)">
            <component :is="fileIcon(att.mime_type)" />
          </n-icon>
        </div>
        <div class="attachment-item__info">
          <div class="attachment-item__name">{{ att.original_name }}</div>
          <div class="attachment-item__size">{{ formatSize(att.file_size) }}</div>
        </div>
        <div class="attachment-item__dl">
          <n-icon size="16"><DownloadOutline /></n-icon>
        </div>
      </a>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NIcon } from 'naive-ui'
import {
  DownloadOutline,
  DocumentOutline,
  ImageOutline,
  VideocamOutline,
  MusicalNotesOutline,
  GridOutline,
  CodeSlashOutline,
} from '@vicons/ionicons5'
import type { NewsAttachment } from '../api/news'

defineProps<{ attachments: NewsAttachment[] }>()
const { t } = useI18n()

function fileIcon(mime: string | null) {
  if (!mime) return DocumentOutline
  if (mime.startsWith('image/')) return ImageOutline
  if (mime.startsWith('video/')) return VideocamOutline
  if (mime.startsWith('audio/')) return MusicalNotesOutline
  if (mime.includes('zip') || mime.includes('rar') || mime.includes('7z') || mime.includes('tar')) return DocumentOutline
  if (mime.includes('spreadsheet') || mime.includes('excel') || mime.includes('csv')) return GridOutline
  if (mime.includes('json') || mime.includes('xml') || mime.includes('javascript') || mime.includes('html')) return CodeSlashOutline
  return DocumentOutline
}

function iconColor(mime: string | null): string {
  if (!mime) return 'var(--color-text-muted)'
  if (mime.startsWith('image/')) return '#10b981'
  if (mime.startsWith('video/')) return '#8b5cf6'
  if (mime.startsWith('audio/')) return '#f59e0b'
  if (mime.includes('zip') || mime.includes('rar') || mime.includes('tar')) return '#f97316'
  if (mime.includes('spreadsheet') || mime.includes('excel')) return '#22c55e'
  if (mime.includes('pdf')) return '#ef4444'
  return 'var(--color-text-muted)'
}

function formatSize(bytes: number | null): string {
  if (!bytes) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}
</script>

<style scoped>
.attachments {
  margin-top: 32px;
  padding-top: 28px;
  border-top: 1px solid var(--color-border);
}

.attachments__title {
  margin: 0 0 12px;
  font-size: 15px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--color-text-muted);
}

.attachments__list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.attachment-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  border-radius: var(--radius-md);
  background: var(--color-bg-muted);
  border: 1px solid var(--color-border);
  text-decoration: none;
  color: var(--color-text);
  transition: background 0.15s, border-color 0.15s;
}

.attachment-item:hover {
  background: var(--color-surface-hover, var(--color-bg-muted));
  border-color: var(--color-brand-sky);
}

.attachment-item__icon {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  display: flex;
  align-items: center;
  justify-content: center;
}

.attachment-item__info {
  flex: 1;
  min-width: 0;
}

.attachment-item__name {
  font-size: 14px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.attachment-item__size {
  font-size: 12px;
  color: var(--color-text-muted);
  margin-top: 1px;
}

.attachment-item__dl {
  flex-shrink: 0;
  color: var(--color-text-subtle);
}
</style>
