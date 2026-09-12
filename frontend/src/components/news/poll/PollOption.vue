<template>
  <div
    :class="[
      'news-poll__option',
      { 'news-poll__option--selected': selected },
      { 'news-poll__option--voted': hasVoted },
      { 'news-poll__option--grid-item': hasImages },
      { 'news-poll__option--interactive': isInteractive },
    ]"
  >
    <template v-if="hasImages">
      <HtmlImageLightbox
        v-if="opt.image_url"
        class="news-poll__option-img-wrap"
        stop-image-click
      >
        <button
          type="button"
          class="news-poll__option-image-trigger"
          :aria-label="t('news.poll.openOptionImage', { number: optionIndex + 1 })"
          :data-lightbox-src="opt.image_url"
          :data-lightbox-alt="optionLabel"
        >
          <img
            :src="opt.image_url"
            :alt="optionLabel"
            class="news-poll__option-img"
          >
        </button>
      </HtmlImageLightbox>
      <component
        :is="isInteractive ? 'label' : 'div'"
        class="news-poll__option-grid-content news-poll__option-select"
        :for="isInteractive ? inputId : undefined"
      >
        <div class="news-poll__option-main">
          <input
            v-if="isInteractive"
            :id="inputId"
            :type="question.is_multiple ? 'checkbox' : 'radio'"
            :name="'poll-' + question.id"
            :value="opt.id"
            :checked="selected"
            :aria-label="optionLabel"
            class="news-poll__input"
            @change="$emit('opt-change', opt.id)"
          >
          <span class="news-poll__option-text">{{ opt.text || '' }}</span>
          <n-tag
            v-if="hasVoted && selected"
            size="tiny"
            type="success"
            round
          >
            {{ t('news.poll.yourAnswer') }}
          </n-tag>
        </div>
        <div
          v-if="canSeeResults && opt.votes_percent !== undefined && opt.votes_percent !== null"
          class="news-poll__option-results"
        >
          <div
            class="news-poll__progress-bg"
            :style="{ width: opt.votes_percent + '%' }"
          />
          <span class="news-poll__percent">{{ opt.votes_percent.toFixed(1) }}%</span>
          <span class="news-poll__votes-count">({{ opt.votes_count }})</span>
        </div>
      </component>
    </template>

    <template v-else>
      <component
        :is="isInteractive ? 'label' : 'div'"
        class="news-poll__option-row news-poll__option-select"
        :for="isInteractive ? inputId : undefined"
      >
        <div class="news-poll__option-main">
          <input
            v-if="isInteractive"
            :id="inputId"
            :type="question.is_multiple ? 'checkbox' : 'radio'"
            :name="'poll-' + question.id"
            :value="opt.id"
            :checked="selected"
            :aria-label="optionLabel"
            class="news-poll__input"
            @change="$emit('opt-change', opt.id)"
          >
          <span class="news-poll__option-text">{{ opt.text || '' }}</span>
          <n-tag
            v-if="hasVoted && selected"
            size="tiny"
            type="success"
            round
          >
            {{ t('news.poll.yourAnswer') }}
          </n-tag>
        </div>
        <span
          v-if="canSeeResults && opt.votes_percent !== undefined && opt.votes_percent !== null"
          class="news-poll__percent"
        >
          {{ opt.votes_percent.toFixed(1) }}%
        </span>
      </component>
      <PollProgress
        v-if="canSeeResults && opt.votes_percent !== undefined && opt.votes_percent !== null"
        :percent="opt.votes_percent"
        :votes-count="opt.votes_count"
        :option-label="optionLabel"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NTag } from 'naive-ui'
import type { NewsPollOptionPublic, NewsPollQuestionPublic } from '../../../api/news'
import HtmlImageLightbox from '../../HtmlImageLightbox.vue'
import PollProgress from './PollProgress.vue'

const props = defineProps<{
  opt: NewsPollOptionPublic
  question: NewsPollQuestionPublic
  hasImages: boolean
  selected: boolean
  hasVoted: boolean
  submitting: boolean
  isInteractive: boolean
  canSeeResults: boolean
  optionIndex: number
}>()

const { t } = useI18n()
const inputId = computed(() => `poll-${props.question.id}-option-${props.opt.id}`)
const optionLabel = computed(() => props.opt.text || t('news.poll.optionNumber', { number: props.optionIndex + 1 }))

defineEmits<{
  (e: 'opt-change', optId: string): void
}>()
</script>

<style scoped>
.news-poll__option {
  position: relative;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 10px 12px;
  cursor: default;
  background: var(--color-bg);
  transition: background 0.15s ease;
}

.news-poll__option--interactive:hover {
  background: var(--color-bg-hover, rgba(0, 0, 0, 0.03));
}

.news-poll__option--selected {
  border-color: var(--color-primary, #2080f0);
  background: rgba(32, 128, 240, 0.06);
}

.news-poll__option-select {
  display: block;
  min-width: 0;
}

.news-poll__option--interactive .news-poll__option-select {
  cursor: pointer;
}

.news-poll__option-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.news-poll__option-main {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
}

.news-poll__option-text {
  font-size: 14px;
}

.news-poll__percent {
  font-weight: 600;
  font-size: 14px;
}

.news-poll__option-img-wrap {
  width: 100%;
  border-radius: var(--radius-sm);
  margin-bottom: 8px;
}

.news-poll__option-image-trigger {
  display: block;
  width: 100%;
  border: 0;
  padding: 0;
  background: transparent;
  cursor: zoom-in;
}

.news-poll__option-img {
  width: 100%;
  height: auto;
  object-fit: contain;
  border-radius: var(--radius-sm);
  display: block;
}

.news-poll__option-results {
  position: relative;
  margin-top: 6px;
  font-size: 12px;
  color: var(--color-text-muted);
}

.news-poll__progress-bg {
  position: absolute;
  inset: 0;
  background: rgba(32, 128, 240, 0.08);
  z-index: 0;
}
</style>
