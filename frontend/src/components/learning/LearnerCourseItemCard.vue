<template>
  <li
    class="item"
    :class="{ 'item--done': item.completed }"
  >
    <span
      class="item__number"
      aria-hidden="true"
    >{{ String(index + 1).padStart(2, '0') }}</span>
    <div class="item__main">
      <div class="item__meta">
        <span class="item__type">
          <n-icon
            :size="16"
            aria-hidden="true"
          >
            <HelpCircleOutline v-if="item.type === 'test'" />
            <PlayCircleOutline v-else-if="isVideo" />
            <DocumentOutline v-else />
          </n-icon>
          {{ item.type === 'test' ? t('learning.course.test') : t('learning.course.material') }}
        </span>
        <span class="item__status">
          <n-icon
            v-if="item.completed"
            :size="16"
            aria-hidden="true"
          ><CheckmarkCircleOutline /></n-icon>
          {{ item.completed ? t('learning.page.done') : t('learning.course.notCompleted') }}
        </span>
      </div>
      <h3 class="item__title">
        {{ item.title }}
      </h3>
      <a
        v-if="item.type === 'material' && item.url"
        :href="item.url"
        target="_blank"
        rel="noopener"
        class="item__link"
      >{{ item.url }}</a>
      <!-- Описание/комментарий материала: тот же rich-конвейер, что у
           описания курса — Markdown → HTML → DOMPurify с iframe-гейтом. -->
      <div
        v-if="renderedDescription"
        class="item__description"
        v-html="renderedDescription"
      />
      <VideoEmbed
        v-if="isVideo && item.url"
        :url="item.url"
        :title="item.title"
        :allowed-origins="origins"
      />
    </div>
    <div class="item__actions">
      <template v-if="item.type === 'material'">
        <n-button
          v-if="item.has_file"
          size="small"
          tag="a"
          :href="materialFileUrl(item.id)"
          target="_blank"
          rel="noopener"
        >
          {{ t('learning.course.openPdf') }}
        </n-button>
        <n-button
          v-if="!item.completed"
          size="small"
          type="primary"
          secondary
          :loading="completing"
          @click="emit('complete', item)"
        >
          {{ t('learning.course.markDone') }}
        </n-button>
      </template>
      <n-button
        v-else
        size="small"
        :type="item.completed ? 'default' : 'primary'"
        @click="emit('openTest', item)"
      >
        {{ item.completed ? t('learning.course.testResults') : t('learning.course.takeTest') }}
      </n-button>
    </div>
  </li>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NIcon } from 'naive-ui'
import { CheckmarkCircleOutline, DocumentOutline, HelpCircleOutline, PlayCircleOutline } from '@vicons/ionicons5'
import { materialFileUrl, type MyCourseItem } from '../../api/learning'
import { parseVideoEmbed } from '../../utils/videoEmbed'
import { mdUnsafe as md } from '../../utils/markdown'
import { sanitizeHtmlAllowIframe } from '../../utils/sanitize'
import VideoEmbed from './VideoEmbed.vue'

const props = defineProps<{
  item: MyCourseItem
  index: number
  origins: string[]
  completing: boolean
}>()
const emit = defineEmits<{
  complete: [item: MyCourseItem]
  openTest: [item: MyCourseItem]
}>()
const { t } = useI18n()
// Keep the same origin gate as CSP; unapproved URLs remain ordinary links.
const isVideo = computed(() => props.item.type === 'material' && !!props.item.url
  && !!parseVideoEmbed(props.item.url, props.origins))
// rich-описание материала — тот же конвейер, что у описания курса
// (на записи бэкенд уже прогнал nh3).
const renderedDescription = computed(() => {
  const raw = props.item.description
  if (!raw) return ''
  return sanitizeHtmlAllowIframe(md.render(raw), props.origins)
})
</script>

<style scoped>
.item {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  gap: 12px 14px;
  padding: 20px;
  color: var(--color-text);
  background: var(--color-surface);
  border: 1px solid var(--color-border-strong);
  border-left: 4px solid var(--color-brand-sky);
  border-radius: var(--radius-lg);
}

.item--done {
  background: color-mix(in srgb, var(--color-success) 7%, var(--color-surface));
  border-color: color-mix(in srgb, var(--color-success) 42%, var(--color-border));
  border-left-color: var(--color-success);
}

.item__number {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  margin-top: 2px;
  color: var(--color-text-muted);
  background: var(--color-bg-muted);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-size: 12px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.item__main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.item__meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 12px;
  line-height: 1.5;
}

.item__type,
.item__status {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--color-text-muted);
}

.item__status {
  padding: 2px 8px;
  font-weight: 600;
  background: var(--color-bg-muted);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
}

.item--done .item__status {
  color: color-mix(in srgb, var(--color-success) 45%, var(--color-text));
  background: color-mix(in srgb, var(--color-success) 12%, var(--color-surface));
  border-color: color-mix(in srgb, var(--color-success) 45%, var(--color-border));
}

.item__title {
  margin: 0;
  font-size: 16px;
  font-weight: 650;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.item__link {
  min-width: 0;
  color: var(--color-text-muted);
  font-size: 13px;
  text-decoration: underline;
  text-underline-offset: 3px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.item__link:focus-visible {
  outline: 2px solid var(--color-brand-sky);
  outline-offset: 3px;
}

/* rich-описание/комментарий материала (Markdown → HTML) */
.item__description {
  margin-top: 2px;
  font-size: 14px;
  line-height: 1.5;
  color: var(--color-text);
}
.item__description :deep(p) {
  margin: 0 0 6px;
}
.item__description :deep(p:last-child) {
  margin-bottom: 0;
}
.item__description :deep(ul),
.item__description :deep(ol) {
  margin: 0 0 6px;
  padding-left: 20px;
}

.item__actions {
  grid-column: 2;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.item__actions:empty {
  display: none;
}

@media (max-width: 639px) {
  .item {
    padding: 16px 12px;
    gap: 12px 10px;
  }

  .item__actions .n-button {
    min-height: 36px;
  }
}
</style>
