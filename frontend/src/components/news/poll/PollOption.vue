<template>
  <!-- eslint-disable-next-line vuejs-accessibility/click-events-have-key-events, vuejs-accessibility/no-static-element-interactions -->
  <div
    :class="[
      'news-poll__option',
      { 'news-poll__option--selected': selected },
      { 'news-poll__option--voted': hasVoted },
      { 'news-poll__option--grid-item': hasImages },
    ]"
    @click="$emit('opt-click', opt.id)"
  >
    <template v-if="hasImages">
      <div
        v-if="opt.image_url"
        class="news-poll__option-img-wrap"
      >
        <img
          :src="opt.image_url"
          :alt="opt.text || ''"
          class="news-poll__option-img"
        >
      </div>
      <div class="news-poll__option-grid-content">
        <div class="news-poll__option-main">
          <input
            v-if="canVote && isAuthenticated"
            :type="question.is_multiple ? 'checkbox' : 'radio'"
            :name="'poll-' + question.id"
            :value="opt.id"
            :checked="selected"
            :aria-label="opt.text || question.text"
            class="news-poll__input"
            @change="$emit('opt-change', opt.id)"
            @click.stop
          >
          <span class="news-poll__option-text">{{ opt.text || '' }}</span>
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
      </div>
    </template>

    <template v-else>
      <div class="news-poll__option-row">
        <div class="news-poll__option-main">
          <input
            v-if="canVote && isAuthenticated"
            :type="question.is_multiple ? 'checkbox' : 'radio'"
            :name="'poll-' + question.id"
            :value="opt.id"
            :checked="selected"
            :aria-label="opt.text || question.text"
            class="news-poll__input"
            @change="$emit('opt-change', opt.id)"
            @click.stop
          >
          <span class="news-poll__option-text">{{ opt.text || '' }}</span>
        </div>
        <span
          v-if="canSeeResults && opt.votes_percent !== undefined && opt.votes_percent !== null"
          class="news-poll__percent"
        >
          {{ opt.votes_percent.toFixed(1) }}%
        </span>
      </div>
      <PollProgress
        v-if="canSeeResults && opt.votes_percent !== undefined && opt.votes_percent !== null"
        :percent="opt.votes_percent"
        :votes-count="opt.votes_count"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import type { NewsPollOptionPublic, NewsPollQuestionPublic } from '../../../api/news'
import PollProgress from './PollProgress.vue'

defineProps<{
  opt: NewsPollOptionPublic
  question: NewsPollQuestionPublic
  hasImages: boolean
  selected: boolean
  hasVoted: boolean
  submitting: boolean
  canVote: boolean
  isAuthenticated: boolean
  canSeeResults: boolean
}>()

defineEmits<{
  (e: 'opt-click', optId: string): void
  (e: 'opt-change', optId: string): void
}>()
</script>

<style scoped>
.news-poll__option {
  position: relative;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 10px 12px;
  cursor: pointer;
  background: var(--color-bg);
  transition: background 0.15s ease;
}

.news-poll__option:hover {
  background: var(--color-bg-hover, rgba(0, 0, 0, 0.03));
}

.news-poll__option--selected {
  border-color: var(--color-primary, #2080f0);
  background: rgba(32, 128, 240, 0.06);
}

.news-poll__option--voted {
  cursor: default;
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
  aspect-ratio: 16 / 10;
  overflow: hidden;
  border-radius: var(--radius-sm);
  margin-bottom: 8px;
}

.news-poll__option-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
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
