<template>
  <div class="versions-list">
    <div
      v-for="v in versions"
      :key="v.id"
      class="version-item"
    >
      <div class="version-item__header">
        <span class="version-item__num">v{{ v.version }}</span>
        <span class="version-item__by">{{ v.changed_by?.full_name ?? '—' }}</span>
        <span class="version-item__date">{{ formatDate(v.created_at, locale) }}</span>
        <span
          v-if="v.change_comment"
          class="version-item__comment"
        >{{ v.change_comment }}</span>
        <n-button
          size="tiny"
          @click="$emit('diff', v.version, currentVersion)"
        >
          {{ t('kb.diff.compare') }}
        </n-button>
        <n-button
          v-if="canRestore && v.version !== currentVersion"
          size="tiny"
          @click="restore(v.version)"
        >
          {{ t('kb.restoreVersion') }}
        </n-button>
      </div>
    </div>
    <EmptyState
      v-if="!versions.length"
      variant="default"
      :title="t('kb.noVersions')"
      description=""
    />
  </div>
</template>

<script setup lang="ts">
import { toRef } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton } from 'naive-ui'
import { formatDate } from '@/utils/formatDate'
import EmptyState from './EmptyState.vue'
import { useKbArticleVersions } from '../composables/useKbArticleVersions'

const props = defineProps<{
  articleId: string
  currentVersion: number
  canRestore: boolean
}>()

defineEmits<{
  (e: 'diff', v1: number, v2: number): void
}>()

const { t, locale } = useI18n()

const { versions, restore } = useKbArticleVersions(toRef(props, 'articleId'))
</script>

<style scoped>
.versions-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.version-item {
  padding: 12px 16px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

.version-item__header {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 13px;
  flex-wrap: wrap;
}

.version-item__num {
  font-weight: 700;
  font-size: 14px;
}

.version-item__comment {
  color: var(--color-text-muted);
  font-style: italic;
}
</style>
