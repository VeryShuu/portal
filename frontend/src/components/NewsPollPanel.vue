<template>
  <div class="u-panel poll-panel">
    <div class="u-panel__title-row">
      <div class="u-panel__title">
        {{ t('news.poll.editor.title') }}
      </div>
      <n-button
        v-if="newsId && poll"
        size="tiny"
        type="error"
        ghost
        :loading="deleting"
        @click="handleDelete"
      >
        {{ t('news.poll.editor.removePoll') }}
      </n-button>
    </div>

    <div
      v-if="!newsId"
      class="u-panel__hint"
      style="color:var(--color-warning,#f0a020)"
    >
      {{ t('news.form.saveFirst') }}
    </div>

    <div
      v-else-if="!poll && !showCreateForm"
      class="poll-empty-state"
    >
      <n-button
        type="primary"
        dashed
        @click="initCreateForm"
      >
        <template #icon>
          <n-icon><AddOutline /></n-icon>
        </template>
        {{ t('news.poll.editor.addPoll') }}
      </n-button>
    </div>

    <div
      v-else-if="newsId"
      class="poll-form"
    >
      <!-- Poll-level settings -->
      <div class="poll-form__settings-grid">
        <n-form-item :label="t('news.poll.editor.resultsVisibility')">
          <n-select
            v-model:value="pollForm.results_visibility"
            :options="visibilityOptions"
            :disabled="hasVotes"
          />
        </n-form-item>

        <n-form-item :label="t('news.poll.editor.closesAt')">
          <n-date-picker
            v-model:value="closesAtMs"
            type="datetime"
            clearable
            style="width: 100%"
          />
        </n-form-item>
      </div>

      <div class="poll-form__checkboxes">
        <n-checkbox
          v-model:checked="pollForm.is_anonymous"
          :disabled="hasVotes"
        >
          {{ t('news.poll.editor.anonymous') }}
        </n-checkbox>
        <n-checkbox
          v-model:checked="pollForm.allow_revote"
          :disabled="hasVotes"
        >
          {{ t('news.poll.editor.allowRevote') }}
        </n-checkbox>
      </div>

      <!-- Questions -->
      <div class="poll-form__questions-section">
        <div class="poll-form__questions-title">
          {{ t('news.poll.editor.questions') }}
          <span class="poll-form__count">({{ pollForm.questions.length }})</span>
        </div>

        <div
          v-for="(q, qIdx) in pollForm.questions"
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
                :disabled="qIdx === pollForm.questions.length - 1 || hasVotes"
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
                :disabled="pollForm.questions.length <= 1 || hasVotes"
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

          <!-- Options -->
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
                      :custom-request="(opts: UploadCustomRequestOptions) => handleOptionImageUpload(opt, opts)"
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
          v-if="pollForm.questions.length < 30"
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
          @click="handleSave"
        >
          {{ t('common.save', 'Сохранить') }}
        </n-button>
        <n-button
          v-if="!poll"
          quaternary
          @click="cancelCreate"
        >
          {{ t('common.cancel', 'Отмена') }}
        </n-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NButton, NIcon, NFormItem, NInput, NSelect, NCheckbox,
  NInputNumber, NDatePicker, NUpload, useMessage,
  type UploadCustomRequestOptions,
} from 'naive-ui'
import {
  AddOutline, CloseOutline, ArrowUpOutline, ArrowDownOutline, CloudUploadOutline,
} from '@vicons/ionicons5'
import { useConfirmDialog } from '../composables/useConfirmDialog'
import {
  useNewsPollQuery,
  useCreateNewsPollMutation,
  useUpdateNewsPollMutation,
  useDeleteNewsPollMutation,
} from '../queries/news'
import { uploadNewsInlineMedia } from '../api/news'
import { parseApiError } from '../utils/parseApiError'

const props = defineProps<{
  newsId?: string
  hasPoll?: boolean
}>()

const { t } = useI18n()
const message = useMessage()
const { confirm } = useConfirmDialog()

const { data: poll } = useNewsPollQuery(() => props.newsId || '', {
  enabled: computed(() => !!props.newsId && !!props.hasPoll),
})

const createMutation = useCreateNewsPollMutation()
const updateMutation = useUpdateNewsPollMutation()
const deleteMutation = useDeleteNewsPollMutation()

const showCreateForm = ref(false)
const saving = ref(false)
const deleting = ref(false)
const uploadingImage = ref(false)

interface OptionForm {
  id?: string
  text: string
  image_url: string
  sort_order: number
}

interface QuestionForm {
  id?: string
  text: string
  sort_order: number
  is_required: boolean
  is_multiple: boolean
  max_choices: number | null
  allow_custom_answer: boolean
  options: OptionForm[]
}

interface PollForm {
  is_anonymous: boolean
  allow_revote: boolean
  results_visibility: 'always' | 'after_vote' | 'after_close' | 'only_admin_editor'
  closes_at: string | null
  questions: QuestionForm[]
}

function makeEmptyQuestion(sort = 0): QuestionForm {
  return {
    text: '',
    sort_order: sort,
    is_required: true,
    is_multiple: false,
    max_choices: null,
    allow_custom_answer: false,
    options: [
      { text: '', image_url: '', sort_order: 0 },
      { text: '', image_url: '', sort_order: 1 },
    ],
  }
}

const pollForm = ref<PollForm>({
  is_anonymous: true,
  allow_revote: false,
  results_visibility: 'after_vote',
  closes_at: null,
  questions: [],
})

const closesAtMs = computed({
  get: () => pollForm.value.closes_at ? new Date(pollForm.value.closes_at).getTime() : null,
  set: (ms: number | null) => {
    pollForm.value.closes_at = ms ? new Date(ms).toISOString() : null
  },
})

const hasVotes = computed(() => !!poll.value && (poll.value.total_voters || 0) > 0)

const visibilityOptions = computed(() => [
  { label: t('news.poll.editor.visibility.always'), value: 'always' },
  { label: t('news.poll.editor.visibility.after_vote'), value: 'after_vote' },
  { label: t('news.poll.editor.visibility.after_close'), value: 'after_close' },
  { label: t('news.poll.editor.visibility.only_admin_editor'), value: 'only_admin_editor' },
])

watch(poll, (p) => {
  if (p) {
    pollForm.value.is_anonymous = p.is_anonymous
    pollForm.value.allow_revote = p.allow_revote
    pollForm.value.results_visibility = p.results_visibility
    pollForm.value.closes_at = p.closes_at || null
    pollForm.value.questions = [...p.questions]
      .sort((a, b) => a.sort_order - b.sort_order)
      .map(q => ({
        id: q.id,
        text: q.text,
        sort_order: q.sort_order,
        is_required: q.is_required,
        is_multiple: q.is_multiple,
        max_choices: q.max_choices || null,
        allow_custom_answer: q.allow_custom_answer,
        options: [...q.options]
          .sort((a, b) => a.sort_order - b.sort_order)
          .map(o => ({
            id: o.id,
            text: o.text || '',
            image_url: o.image_url || '',
            sort_order: o.sort_order,
          })),
      }))
    showCreateForm.value = false
  } else {
    resetForm()
  }
}, { immediate: true })

function resetForm() {
  pollForm.value = {
    is_anonymous: true,
    allow_revote: false,
    results_visibility: 'after_vote',
    closes_at: null,
    questions: [makeEmptyQuestion(0)],
  }
}

function initCreateForm() {
  resetForm()
  showCreateForm.value = true
}

function cancelCreate() {
  showCreateForm.value = false
  resetForm()
}

function addQuestion() {
  if (pollForm.value.questions.length >= 30) return
  pollForm.value.questions.push(makeEmptyQuestion(pollForm.value.questions.length))
}

function removeQuestion(idx: number) {
  if (pollForm.value.questions.length <= 1) return
  pollForm.value.questions.splice(idx, 1)
  pollForm.value.questions.forEach((q, i) => { q.sort_order = i })
}

function moveQuestion(idx: number, direction: -1 | 1) {
  const target = idx + direction
  if (target < 0 || target >= pollForm.value.questions.length) return
  const tmp = pollForm.value.questions[idx]
  pollForm.value.questions[idx] = pollForm.value.questions[target]
  pollForm.value.questions[target] = tmp
  pollForm.value.questions.forEach((q, i) => { q.sort_order = i })
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

async function handleOptionImageUpload(opt: OptionForm, options: UploadCustomRequestOptions) {
  const { file, onFinish, onError } = options
  if (!props.newsId || !file.file) { onError(); return }
  uploadingImage.value = true
  try {
    const res = await uploadNewsInlineMedia(props.newsId, file.file)
    opt.image_url = res.url
    onFinish()
  } catch (e) {
    message.error(parseApiError(e, t))
    onError()
  } finally {
    uploadingImage.value = false
  }
}

function validatePoll(): boolean {
  if (pollForm.value.questions.length < 1) {
    message.error(t('news.poll.editor.minQuestions'))
    return false
  }
  for (const q of pollForm.value.questions) {
    if (!q.text.trim()) {
      message.error(t('news.poll.editor.questionPlaceholder'))
      return false
    }
    if (q.options.length < 2) {
      message.error(t('news.poll.editor.minOptions'))
      return false
    }
    for (const opt of q.options) {
      if (!opt.text.trim() && !opt.image_url.trim()) {
        message.error(t('news.poll.editor.optionTextOrImage'))
        return false
      }
    }
    const texts = q.options.map(o => o.text.trim().toLowerCase()).filter(Boolean)
    if (new Set(texts).size !== texts.length) {
      message.error(t('news.poll.editor.duplicateOptions'))
      return false
    }
  }
  return true
}

async function handleSave() {
  if (!validatePoll() || !props.newsId) return

  saving.value = true
  try {
    const questions = pollForm.value.questions.map((q, qi) => ({
      id: q.id,
      text: q.text.trim(),
      sort_order: qi,
      is_required: q.is_required,
      is_multiple: q.is_multiple,
      max_choices: q.is_multiple ? q.max_choices : null,
      allow_custom_answer: q.allow_custom_answer,
      options: q.options.map((o, oi) => ({
        id: o.id,
        text: o.text.trim() || null,
        image_url: o.image_url.trim() || null,
        sort_order: oi,
      })),
    }))

    const dto = {
      is_anonymous: pollForm.value.is_anonymous,
      allow_revote: pollForm.value.allow_revote,
      results_visibility: pollForm.value.results_visibility,
      closes_at: pollForm.value.closes_at,
      questions,
    }

    if (poll.value) {
      await updateMutation.mutateAsync({ newsId: props.newsId, dto })
    } else {
      await createMutation.mutateAsync({ newsId: props.newsId, dto })
      showCreateForm.value = false
    }
    message.success(t('common.save'))
  } catch (err: unknown) {
    const e = err as { response?: { _data?: { detail?: string } }; message?: string }
    message.error(e?.response?._data?.detail || e?.message || 'Ошибка сохранения')
  } finally {
    saving.value = false
  }
}

async function handleDelete() {
  if (!props.newsId) return
  const ok = await confirm({
    title: t('news.poll.actions.delete'),
    content: t('news.poll.actions.deleteConfirm'),
    positiveText: t('common.delete', 'Удалить'),
    negativeText: t('common.cancel', 'Отмена'),
    type: 'error',
  })
  if (!ok) return

  deleting.value = true
  try {
    await deleteMutation.mutateAsync(props.newsId)
    showCreateForm.value = false
    resetForm()
    message.success(t('news.poll.actions.deleted', 'Опрос удалён'))
  } catch (err: unknown) {
    const e = err as { response?: { _data?: { detail?: string } }; message?: string }
    message.error(e?.response?._data?.detail || e?.message || 'Ошибка удаления')
  } finally {
    deleting.value = false
  }
}
</script>

<style scoped>
.poll-panel {
  margin-top: 20px;
}

.u-panel__title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.poll-empty-state {
  display: flex;
  justify-content: center;
  padding: 16px 0;
}

.poll-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-top: 12px;
}

.poll-form__settings-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.poll-form__checkboxes {
  display: flex;
  flex-direction: row;
  flex-wrap: wrap;
  gap: 16px;
}

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

@media (max-width: 600px) {
  .poll-form__settings-grid {
    grid-template-columns: 1fr;
  }
}
</style>
