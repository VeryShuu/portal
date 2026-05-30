<template>
  <div
    class="news-poll__progressbar-wrap"
  >
    <div
      class="news-poll__progressbar"
      role="progressbar"
      :aria-valuenow="percent"
      aria-valuemin="0"
      aria-valuemax="100"
      :style="{ width: percent + '%' }"
    />
  </div>
  <span class="news-poll__votes-count-inline">
    {{ votesCount }} {{ t('news.poll.voters', { count: votesCount ?? 0 }) }}
  </span>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

defineProps<{
  percent: number
  votesCount: number | null | undefined
}>()
</script>

<style scoped>
.news-poll__progressbar-wrap {
  margin-top: 6px;
  height: 4px;
  background: var(--color-border);
  border-radius: 2px;
  overflow: hidden;
}

.news-poll__progressbar {
  height: 100%;
  background: var(--color-primary, #2080f0);
  transition: width 0.4s ease;
}

.news-poll__votes-count-inline {
  font-size: 11px;
  color: var(--color-text-muted);
  margin-top: 4px;
  display: inline-block;
}
</style>
