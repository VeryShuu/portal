<template>
  <fieldset
    class="news-poll__question-block"
    :disabled="submitting"
  >
    <legend class="news-poll__question">
      <span class="news-poll__question-number">{{ questionIndex + 1 }}.</span>
      {{ question.text }}
      <n-tag
        v-if="!question.is_required"
        size="tiny"
        round
        type="default"
        class="news-poll__question-tag"
      >
        {{ t('news.poll.optional') }}
      </n-tag>
      <n-tag
        v-else
        size="tiny"
        round
        type="error"
        class="news-poll__question-tag"
      >
        {{ t('news.poll.required') }}
      </n-tag>
    </legend>

    <p
      v-if="question.is_multiple && canVote && isAuthenticated && question.max_choices"
      class="news-poll__info"
    >
      {{ t('news.poll.maxChoices', { count: question.max_choices }) }}
    </p>

    <div :class="['news-poll__options', { 'news-poll__options--grid': hasImages }]">
      <PollOption
        v-for="opt in sortedOpts"
        :key="opt.id"
        :opt="opt"
        :question="question"
        :has-images="hasImages"
        :selected="selectedIds.includes(opt.id)"
        :has-voted="hasVoted"
        :submitting="submitting"
        :can-vote="canVote"
        :is-authenticated="isAuthenticated"
        :can-see-results="canSeeResults"
        @opt-click="$emit('opt-click', question, $event)"
        @opt-change="$emit('opt-change', question, $event)"
      />

      <div
        v-if="question.allow_custom_answer"
        class="news-poll__option news-poll__option--custom"
      >
        <div class="news-poll__option-row">
          <div class="news-poll__option-main news-poll__option-main--custom">
            <input
              v-if="canVote && isAuthenticated"
              :type="question.is_multiple ? 'checkbox' : 'radio'"
              :name="'poll-' + question.id"
              :checked="customChecked"
              class="news-poll__input"
              @change="$emit('custom-toggle', question)"
              @click.stop
            >
            <n-input
              :value="customText"
              :placeholder="t('news.poll.customPlaceholder')"
              maxlength="500"
              :disabled="!canVote || !isAuthenticated"
              size="small"
              @input="onCustomInput"
            />
          </div>
        </div>
      </div>
    </div>

    <div
      v-if="canSeeResults && question.custom_answers && question.custom_answers.length"
      class="news-poll__custom-answers"
    >
      <div class="news-poll__custom-answers-title">
        {{ t('news.poll.customAnswersTitle') }}
      </div>
      <ul class="news-poll__custom-answers-list">
        <li
          v-for="(ca, ci) in question.custom_answers"
          :key="ci"
          class="news-poll__custom-answer"
        >
          <span class="news-poll__custom-answer-text">«{{ ca.text }}»</span>
          <span
            v-if="ca.voter_name"
            class="news-poll__custom-answer-author"
          >
            — {{ ca.voter_name }}
          </span>
        </li>
      </ul>
    </div>
  </fieldset>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NTag, NInput } from 'naive-ui'
import type { NewsPollQuestionPublic, NewsPollOptionPublic } from '../../../api/news'
import PollOption from './PollOption.vue'

const { t } = useI18n()

const props = defineProps<{
  question: NewsPollQuestionPublic
  questionIndex: number
  sortedOpts: NewsPollOptionPublic[]
  hasImages: boolean
  selectedIds: string[]
  customText: string
  customChecked: boolean
  hasVoted: boolean
  submitting: boolean
  canVote: boolean
  isAuthenticated: boolean
  canSeeResults: boolean
}>()

const emit = defineEmits<{
  (e: 'opt-click', question: NewsPollQuestionPublic, optId: string): void
  (e: 'opt-change', question: NewsPollQuestionPublic, optId: string): void
  (e: 'custom-toggle', question: NewsPollQuestionPublic): void
  (e: 'custom-input', question: NewsPollQuestionPublic, text: string): void
}>()

function onCustomInput(val: string) {
  emit('custom-input', props.question, val)
}
</script>

<style scoped>
.news-poll__question-block {
  border: none;
  padding: 0;
  margin: 0;
}

.news-poll__question {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text);
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.news-poll__question-number {
  color: var(--color-text-muted);
}

.news-poll__question-tag {
  margin-left: 6px;
}

.news-poll__info {
  font-size: 12px;
  color: var(--color-text-muted);
  margin-bottom: 8px;
}

.news-poll__options {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.news-poll__options--grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 12px;
}

.news-poll__option--custom {
  background: var(--color-bg);
  border-style: dashed;
}

.news-poll__option-main--custom {
  width: 100%;
}

.news-poll__custom-answers {
  margin-top: 10px;
  padding: 10px 12px;
  background: var(--color-bg);
  border-radius: var(--radius-sm);
}

.news-poll__custom-answers-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-muted);
  margin-bottom: 6px;
}

.news-poll__custom-answers-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.news-poll__custom-answer-text {
  font-size: 13px;
}

.news-poll__custom-answer-author {
  font-size: 12px;
  color: var(--color-text-muted);
  margin-left: 4px;
}

.news-poll__option {
  position: relative;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 10px 12px;
  cursor: pointer;
  background: var(--color-bg);
  transition: background 0.15s ease;
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
</style>
