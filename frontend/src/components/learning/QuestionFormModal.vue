<template>
  <n-modal
    class="learning-question-modal"
    :show="show"
    preset="card"
    :title="question ? t('learning.question.editTitle') : t('learning.question.addTitle')"
    style="max-width: 640px"
    @update:show="emit('update:show', $event)"
  >
    <n-form label-placement="top">
      <n-form-item
        :label="t('learning.question.textField')"
        required
      >
        <n-input
          v-model:value="form.text"
          type="textarea"
          :rows="2"
          :maxlength="8000"
        />
      </n-form-item>
      <n-form-item :label="t('learning.question.multiLabel')">
        <n-switch v-model:value="form.multi" />
        <n-text
          depth="3"
          style="margin-left: 8px; font-size: 12px"
        >
          {{ form.multi ? t('learning.question.multiHint') : t('learning.question.singleHint') }}
        </n-text>
      </n-form-item>

      <div class="options-head">
        <span class="options-label">{{ t('learning.question.options') }}</span>
        <n-button
          size="tiny"
          :disabled="form.options.length >= 12"
          @click="addOption"
        >
          <template #icon>
            <n-icon><AddOutline /></n-icon>
          </template>
          {{ t('learning.question.addOption') }}
        </n-button>
      </div>

      <div class="options-edit">
        <div
          v-for="(opt, idx) in form.options"
          :key="idx"
          class="option-row"
        >
          <!-- «Ровно один правильный» — радио (выбор физически один),
               «несколько» — чекбоксы; интуитивно и совпадает с 422 бэкенда -->
          <n-radio
            v-if="!form.multi"
            :checked="opt.is_correct"
            name="learning-correct-option"
            :title="t('learning.question.correctFlag')"
            @update:checked="selectSingleCorrect(idx)"
          />
          <n-checkbox
            v-else
            :checked="opt.is_correct"
            :title="t('learning.question.correctFlag')"
            @update:checked="opt.is_correct = $event"
          />
          <n-input
            v-model:value="opt.text"
            size="small"
            :placeholder="t('learning.question.optionPlaceholder')"
            :maxlength="2000"
          />
          <n-button
            quaternary
            size="tiny"
            type="error"
            :disabled="form.options.length <= 2"
            @click="form.options.splice(idx, 1)"
          >
            <n-icon><CloseOutline /></n-icon>
          </n-button>
        </div>
      </div>
    </n-form>

    <template #footer>
      <div class="modal-actions">
        <n-button @click="emit('update:show', false)">
          {{ t('common.cancel') }}
        </n-button>
        <n-button
          type="primary"
          :loading="saving"
          @click="submit"
        >
          {{ t('common.save') }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NButton,
  NCheckbox,
  NForm,
  NFormItem,
  NIcon,
  NInput,
  NModal,
  NRadio,
  NSwitch,
  NText,
  useMessage,
} from 'naive-ui'
import { AddOutline, CloseOutline } from '@vicons/ionicons5'
import {
  useAddQuestionMutation,
  useUpdateQuestionMutation,
} from '../../queries/learning'
import type { LearningQuestionOut } from '../../api/learning'
import { useMutationErrorToasts } from '../../composables/useMutationErrorToasts'

const props = defineProps<{ show: boolean; itemId: string | null; question: LearningQuestionOut | null }>()
const emit = defineEmits<{ (e: 'update:show', value: boolean): void }>()

const { t } = useI18n()
const message = useMessage()

const form = reactive({
  text: '',
  multi: false,
  options: [
    { text: '', is_correct: true },
    { text: '', is_correct: false },
  ],
})

watch(
  () => [props.show, props.question] as const,
  ([show, q]) => {
    if (!show) return
    if (q) {
      form.text = q.text
      form.multi = q.multi
      form.options = q.options.map((o) => ({ text: o.text, is_correct: o.is_correct }))
    } else {
      form.text = ''
      form.multi = false
      form.options = [
        { text: '', is_correct: true },
        { text: '', is_correct: false },
      ]
    }
  },
)

const addMut = useAddQuestionMutation()
const updateMut = useUpdateQuestionMutation()
const saving = ref(false)

useMutationErrorToasts([addMut.error, updateMut.error], (text) => message.error(text), t)

function addOption() {
  form.options.push({ text: '', is_correct: false })
}

function selectSingleCorrect(idx: number) {
  form.options.forEach((o, i) => {
    o.is_correct = i === idx
  })
}

// Переключение в «ровно один правильный»: оставляем первую отмеченную
// галочку, остальные снимаем — иначе сохранение упиралось бы в 422
// бэкенда (single = ровно один is_correct).
watch(
  () => form.multi,
  (multi) => {
    if (multi) return
    let seen = false
    for (const o of form.options) {
      if (o.is_correct && !seen) {
        seen = true
      } else {
        o.is_correct = false
      }
    }
    if (!seen && form.options[0]) form.options[0].is_correct = true
  },
)

async function submit() {
  if (!props.itemId) return
  if (!form.text.trim()) {
    message.error(t('learning.question.textRequired'))
    return
  }
  if (form.options.some((o) => !o.text.trim())) {
    message.error(t('learning.question.optionTextRequired'))
    return
  }
  const body = {
    text: form.text.trim(),
    multi: form.multi,
    options: form.options.map((o) => ({ text: o.text.trim(), is_correct: o.is_correct })),
  }
  saving.value = true
  try {
    if (props.question) {
      await updateMut.mutateAsync({ itemId: props.itemId, questionId: props.question.id, body })
    } else {
      await addMut.mutateAsync({ itemId: props.itemId, body })
    }
    message.success(t('common.saved'))
    emit('update:show', false)
  } catch {
    // ошибка уже показана в watch
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.options-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.options-label {
  font-size: 14px;
  font-weight: 500;
}

.options-edit {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.option-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
