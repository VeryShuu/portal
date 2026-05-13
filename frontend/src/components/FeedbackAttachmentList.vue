<template>
  <div class="fb-atts">
    <h4 class="fb-atts__title">{{ t('feedback.attachmentsSection') }}</h4>
    <ul class="fb-atts__list">
      <li v-for="att in attachments" :key="att.id" class="fb-atts__item">
        <a
          v-if="isImage(att.mime_type)"
          :href="att.download_url"
          target="_blank"
          rel="noopener noreferrer"
          class="fb-atts__thumb-link"
          :title="att.original_name"
        >
          <img :src="att.download_url" :alt="att.original_name" class="fb-atts__thumb" loading="lazy" />
        </a>
        <a
          v-else
          :href="att.download_url"
          target="_blank"
          rel="noopener noreferrer"
          class="fb-atts__file"
        >
          <n-icon size="20"><DocumentOutline /></n-icon>
          <span class="fb-atts__name" :title="att.original_name">{{ att.original_name }}</span>
        </a>
        <span class="fb-atts__size">{{ formatSize(att.size_bytes) }}</span>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NIcon } from 'naive-ui'
import { DocumentOutline } from '@vicons/ionicons5'
import type { FeedbackAttachmentOut } from '../api/feedback'
import { formatSize } from '@/utils/formatSize'

defineProps<{ attachments: FeedbackAttachmentOut[] }>()

const { t } = useI18n()

function isImage(mime: string | null): boolean {
  if (!mime) return false
  return mime.startsWith('image/') && mime !== 'image/svg+xml'
}

</script>

<style scoped>
.fb-atts {
  margin-top: 12px;
}
.fb-atts__title {
  margin: 0 0 8px;
  font-size: 14px;
}
.fb-atts__list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.fb-atts__item {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  max-width: 180px;
}
.fb-atts__thumb-link {
  display: block;
  border: 1px solid var(--divider-color, #e5e5e5);
  border-radius: 6px;
  overflow: hidden;
  line-height: 0;
}
.fb-atts__thumb {
  width: 160px;
  height: 120px;
  object-fit: cover;
  background: var(--color-bg-elevated, #f7f7f8);
  display: block;
}
.fb-atts__file {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  border: 1px solid var(--divider-color, #e5e5e5);
  border-radius: 6px;
  text-decoration: none;
  color: inherit;
  max-width: 180px;
}
.fb-atts__file:hover {
  background: var(--color-bg-elevated, #f7f7f8);
}
.fb-atts__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
}
.fb-atts__size {
  font-size: 11px;
  color: var(--color-text-secondary, #888);
}
</style>
