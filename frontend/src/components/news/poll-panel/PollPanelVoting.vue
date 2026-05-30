<template>
  <div class="poll-form__questions-section">
    <div class="poll-form__questions-title">
      {{ t('news.poll.editor.questions') }}
      <span class="poll-form__count">({{ form.questions.length }})</span>
    </div>

    <div
      v-for="(q, qIdx) in form.questions"
      :key="qIdx"
      class="poll-form__question-card"
    >
      <div class="poll-form__question-card-header">
        <span class="poll-form__question-card-idx">
          {{ t('news.poll.editor.question') }} #{{ qIdx + 1 }}
        </span>
        <div class="poll-form__question-card-actions">
          <n-button
            size="tiny"
            quaternary
            circle
            :disabled="qIdx === 0 || hasVotes"
            @click="moveQuestion(qIdx, -1)"
          >
            <template #icon>
              <n-icon><ArrowUpOutline /></n-icon>
            </template>
          </n-button>
          <n-button
            size="tiny"
            quaternary
            circle
            :disabled="qIdx === form.questions.length - 1 || hasVotes"
            @click="moveQuestion(qIdx, 1)"
          >
            <template #icon>
              <n-icon><ArrowDownOutline /></n-icon>
            </template>
          </n-button>
          <n-button
            size="tiny"
            type="error"
            quaternary
            circle
            :disabled="form.questions.length <= 1 || hasVotes"
            @click="removeQuestion(qIdx)"
          >
            <template #icon>
              <n-icon><CloseOutline /></n-icon>
            </template>
          </n-button>
        </div>
      </div>

      <n-form-item
        :label="t('news.poll.editor.questionText')"
        required
      >
        <n-input
          v-model:value="q.text"
          :placeholder="t('news.poll.editor.questionPlaceholder')"
          maxlength="500"
          show-count
        />
      </n-form-item>

      <div class="poll-form__question-flags">
        <n-checkbox
          v-model:checked="q.is_required"
          :disabled="hasVotes"
        >
          {{ t('news.poll.editor.required') }}
        </n-checkbox>
        <n-checkbox
          v-model:checked="q.is_multiple"
          :disabled="hasVotes"
          @update:checked="onMultipleToggle(q)"
        >
          {{ t('news.poll.editor.multiple') }}
        </n-checkbox>
        <n-checkbox
          v-model:checked="q.allow_custom_answer"
          :disabled="hasVotes"
        >
          {{ t('news.poll.editor.allowCustomAnswer') }}
        </n-checkbox>
      </div>

      <n-form-item
        v-if="q.is_multiple"
        :label="t('news.poll.editor.maxChoices')"
        style="max-width: 220px"
      >
        <n-input-number
          v-model:value="q.max_choices"
          :min="1"
          :max="q.options.length + (q.allow_custom_answer ? 1 : 0)"
          clearable
          :disabled="hasVotes"
        />
      </n-form-item>

      <div class="poll-form__options-section">
        <div class="poll-form__options-title">
          {{ t('news.poll.editor.options') }}
          <span class="poll-form__count">({{ q.options.length }})</span>
        </div>
        <div class="poll-form__options-list">
          <div
            v-for="(opt, oIdx) in q.options"
            :key="oIdx"
            class="poll-form__option-item"
          >
            <div class="poll-form__option-sort-actions">
              <n-button
                size="tiny"
                quaternary
                circle
                :disabled="oIdx === 0 || hasVotes"
                @click="moveOption(q, oIdx, -1)"
              >
                <template #icon>
                  <n-icon><ArrowUpOutline /></n-icon>
                </template>
              </n-button>
              <n-button
                size="tiny"
                quaternary
                circle
                :disabled="oIdx === q.options.length - 1 || hasVotes"
                @click="moveOption(q, oIdx, 1)"
              >
                <template #icon>
                  <n-icon><ArrowDownOutline /></n-icon>
                </template>
              </n-button>
            </div>
            <div class="poll-form__option-inputs">
              <n-input
                v-model:value="opt.text"
                :placeholder="t('news.poll.editor.textPlaceholder')"
                maxlength="200"
                show-count
              />
              <div class="poll-form__option-image-row">
                <div
                  v-if="opt.image_url"
                  class="poll-form__option-image-preview"
                >
                  <img
                    :src="opt.image_url"
                    :alt="opt.text || ''"
                  >
                  <n-button
                    size="tiny"
                    type="error"
                    quaternary
                    circle
                    :disabled="hasVotes"
                    class="poll-form__option-image-remove"
                    @click="opt.image_url = ''"
                  >
                    <template #icon>
                      <n-icon><CloseOutline /></n-icon>
                    </template>
                  </n-button>
                </div>
                <n-upload
                  v-else
                  :show-file-list="false"
                  :custom-request="(uploadOpts) => onImageUpload(opt, uploadOpts)"
                  :disabled="hasVotes || !newsId || uploadingImage"
                  accept="image/*"
                >
                  <n-button
                    size="small"
                    dashed
                    :loading="uploadingImage"
                    :disabled="hasVotes || !newsId"
                  >
                    <template #icon>
                      <n-icon><CloudUploadOutline /></n-icon>
                    </template>
                    {{ t('news.poll.editor.uploadImage') }}
                  </n-button>
                </n-upload>
              </div>
            </div>
            <n-button
              size="small"
              type="error"
              quaternary
              circle
              :disabled="q.options.length <= 2 || hasVotes"
              @click="removeOption(q, oIdx)"
            >
              <template #icon>
                <n-icon><CloseOutline /></n-icon>
              </template>
            </n-button>
          </div>
        </div>
        <n-button
          v-if="q.options.length < 20"
          size="small"
          dashed
          type="primary"
          :disabled="hasVotes"
          style="margin-top: 8px;"
          @click="addOption(q)"
        >
          <template #icon>
            <n-icon><AddOutline /></n-icon>
          </template>
          {{ t('news.poll.editor.addOption') }}
        </n-button>
      </div>
    </div>

    <n-button
      v-if="form.questions.length < 30"
      size="small"
      dashed
      type="primary"
      :disabled="hasVotes"
      style="margin-top: 12px;"
      @click="addQuestion"
    >
      <template #icon>
        <n-icon><AddOutline /></n-icon>
      </template>
      {{ t('news.poll.editor.addQuestion') }}
    </n-button>
  </div>

  <div class="poll-form__actions">
    <n-button
      type="primary"
      :loading="saving"
      @click="$emit('save')"
    >
      {{ t('common.save', 'Сохранить') }}
    </n-button>
    <n-button
      v-if="showCancelButton"
      quaternary
      @click="$emit('cancel')"
    >
      {{ t('common.cancel', 'Отмена') }}
    </n-button>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import {
  NButton, NIcon, NFormItem, NInput, NCheckbox,
  NInputNumber, NUpload, type UploadCustomRequestOptions,
} from 'naive-ui'
import {
  AddOutline, CloseOutline, ArrowUpOutline, ArrowDownOutline, CloudUploadOutline,
} from '@vicons/ionicons5'
import { makeEmptyQuestion, type PollForm, type QuestionForm, type OptionForm } from './composables/usePollPanelState'

const props = defineProps<{
  form: PollForm
  hasVotes: boolean
  uploadingImage: boolean
  newsId?: string
  saving: boolean
  showCancelButton: boolean
  onImageUpload: (opt: OptionForm, options: UploadCustomRequestOptions) => Promise<void>
}>()

defineEmits<{
  save: []
  cancel: []
}>()

const { t } = useI18n()

function addQuestion() {
  if (props.form.questions.length >= 30) return
  props.form.questions.push(makeEmptyQuestion(props.form.questions.length))
}

function removeQuestion(idx: number) {
  if (props.form.questions.length <= 1) return
  props.form.questions.splice(idx, 1)
  props.form.questions.forEach((q, i) => { q.sort_order = i })
}

function moveQuestion(idx: number, direction: -1 | 1) {
  const target = idx + direction
  if (target < 0 || target >= props.form.questions.length) return
  const tmp = props.form.questions[idx]
  props.form.questions[idx] = props.form.questions[target]
  props.form.questions[target] = tmp
  props.form.questions.forEach((q, i) => { q.sort_order = i })
}

function onMultipleToggle(q: QuestionForm) {
  if (!q.is_multiple) {
    q.max_choices = null
  }
}

function addOption(q: QuestionForm) {
  if (q.options.length >= 20) return
  q.options.push({ text: '', image_url: '', sort_order: q.options.length })
}

function removeOption(q: QuestionForm, idx: number) {
  if (q.options.length <= 2) return
  q.options.splice(idx, 1)
  q.options.forEach((o, i) => { o.sort_order = i })
}

function moveOption(q: QuestionForm, idx: number, direction: -1 | 1) {
  const target = idx + direction
  if (target < 0 || target >= q.options.length) return
  const tmp = q.options[idx]
  q.options[idx] = q.options[target]
  q.options[target] = tmp
  q.options.forEach((o, i) => { o.sort_order = i })
}
</script>

<style scoped>
.poll-form__questions-section {
  border-top: 1px solid var(--color-border);
  padding-top: 16px;
}

.poll-form__questions-title {
  font-size: 14px;
  font-weight: 700;
  margin-bottom: 12px;
}

.poll-form__count {
  font-weight: 500;
  color: var(--color-text-muted);
  margin-left: 4px;
}

.poll-form__question-card {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 14px;
  margin-bottom: 14px;
  background: var(--color-bg-card);
}

.poll-form__question-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.poll-form__question-card-idx {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-muted);
}

.poll-form__question-card-actions {
  display: flex;
  gap: 4px;
}

.poll-form__question-flags {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  margin-bottom: 10px;
}

.poll-form__options-section {
  border-top: 1px dashed var(--color-border);
  padding-top: 12px;
  margin-top: 8px;
}

.poll-form__options-title {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 10px;
}

.poll-form__options-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.poll-form__option-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-bg);
}

.poll-form__option-sort-actions {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.poll-form__option-inputs {
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex-grow: 1;
}

.poll-form__option-image-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.poll-form__option-image-preview {
  position: relative;
  display: inline-block;
}

.poll-form__option-image-preview img {
  display: block;
  max-width: 120px;
  max-height: 80px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border);
  object-fit: cover;
}

.poll-form__option-image-remove {
  position: absolute;
  top: -6px;
  right: -6px;
  background: var(--color-bg);
}

.poll-form__actions {
  display: flex;
  gap: 12px;
  border-top: 1px solid var(--color-border);
  padding-top: 16px;
}
</style>
