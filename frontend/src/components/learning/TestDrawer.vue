<template>
  <n-drawer
    class="learning-test-drawer"
    :show="show"
    :width="drawerWidth"
    placement="right"
    @update:show="emit('update:show', $event)"
  >
    <n-drawer-content
      :title="t('learning.test.title')"
      closable
    >
      <!-- Ревью 2026-08-30: ошибка загрузки — не пустой drawer, а alert с retry -->
      <n-alert
        v-if="show && query.isError.value"
        type="error"
        class="drawer-error"
      >
        {{ t('learning.admin.loadError') }}
        <n-button
          size="tiny"
          quaternary
          @click="query.refetch()"
        >
          {{ t('learning.page.retry') }}
        </n-button>
      </n-alert>
      <n-spin :show="query.isLoading.value">
        <template v-if="config">
          <n-form
            label-placement="top"
            class="settings-form"
          >
            <div class="settings-grid">
              <n-form-item
                :label="t('learning.test.passScore')"
                required
              >
                <n-input-number
                  v-model:value="settings.passScore"
                  :min="0"
                  :max="100"
                  style="width: 100%"
                />
              </n-form-item>
              <n-form-item :label="t('learning.test.maxAttempts')">
                <n-input-number
                  v-model:value="settings.maxAttempts"
                  :min="0"
                  :max="100"
                  style="width: 100%"
                />
              </n-form-item>
            </div>
            <n-form-item :label="t('learning.test.timeLimit')">
              <n-input-number
                v-model:value="settings.timeLimit"
                :min="1"
                :max="600"
                :placeholder="t('learning.test.timeLimitHint')"
                style="width: 100%"
                clearable
              />
            </n-form-item>
            <n-form-item :label="t('learning.test.shuffleQuestions')">
              <n-switch v-model:value="settings.shuffleQuestions" />
            </n-form-item>
            <n-form-item :label="t('learning.test.shuffleAnswers')">
              <n-switch v-model:value="settings.shuffleAnswers" />
            </n-form-item>
            <n-button
              type="primary"
              size="small"
              :loading="settingsMut.isPending.value"
              @click="saveSettings"
            >
              {{ t('common.save') }}
            </n-button>
            <n-text
              depth="3"
              style="display:block;margin-top:8px;font-size:12px"
            >
              {{ t('learning.test.maxAttemptsHint') }}
            </n-text>
          </n-form>

          <n-divider />

          <div class="questions-head">
            <h3 class="section-title">
              {{ t('learning.test.questions') }}
            </h3>
            <div class="head-buttons">
              <n-button
                size="small"
                quaternary
                @click="downloadTemplate"
              >
                {{ t('learning.test.import.template') }}
              </n-button>
              <n-button
                size="small"
                @click="pickImportFile"
              >
                {{ t('learning.test.import.button') }}
              </n-button>
              <n-button
                size="small"
                type="primary"
                @click="openAdd"
              >
                <template #icon>
                  <n-icon><AddOutline /></n-icon>
                </template>
                {{ t('learning.test.addQuestion') }}
              </n-button>
            </div>
          </div>
          <input
            ref="importFileInput"
            type="file"
            accept=".xlsx"
            class="import-input"
            :aria-label="t('learning.test.import.button')"
            @change="onImportFile"
          >

          <n-empty
            v-if="config.questions.length === 0"
            :description="t('learning.test.noQuestions')"
          />
          <div
            v-else
            class="questions-list"
          >
            <div
              v-for="(q, idx) in config.questions"
              :key="q.id"
              class="question-card"
            >
              <div class="question-head">
                <span class="question-num">{{ idx + 1 }}.</span>
                <span class="question-text">{{ q.text }}</span>
                <n-tag
                  size="tiny"
                  :bordered="false"
                  :type="q.multi ? 'info' : 'default'"
                >
                  {{ q.multi ? t('learning.test.multi') : t('learning.test.single') }}
                </n-tag>
              </div>
              <ul class="options-list">
                <li
                  v-for="o in q.options"
                  :key="o.id"
                  :class="{ correct: o.is_correct }"
                >
                  {{ o.text }}
                </li>
              </ul>
              <div class="question-actions">
                <n-button
                  size="tiny"
                  @click="openEdit(q)"
                >
                  {{ t('common.edit') }}
                </n-button>
                <n-popconfirm
                  :show-icon="false"
                  @positive-click="removeQuestion(q.id)"
                >
                  <template #trigger>
                    <n-button
                      size="tiny"
                      type="error"
                      quaternary
                      :loading="deleteMut.isPending.value"
                    >
                      {{ t('common.delete') }}
                    </n-button>
                  </template>
                  {{ t('learning.question.deleteConfirm') }}
                </n-popconfirm>
              </div>
            </div>
          </div>
        </template>
      </n-spin>

      <QuestionFormModal
        v-model:show="formOpen"
        :item-id="itemId"
        :question="editingQuestion"
      />

      <n-modal
        v-model:show="importPreviewOpen"
        preset="card"
        :title="t('learning.test.import.previewTitle')"
        style="max-width: 680px"
      >
        <template v-if="importPreview">
          <n-alert
            v-if="importPreview.errors.length"
            type="warning"
            :show-icon="true"
            class="import-errors"
          >
            <p class="import-errors__title">
              {{ t('learning.test.import.errorsTitle', { count: importPreview.errors.length }) }}
            </p>
            <ul class="import-errors__list">
              <li
                v-for="err in importPreview.errors"
                :key="err.row"
              >
                {{ t('learning.test.import.errorRow', { row: err.row }) }} — {{ err.message }}
              </li>
            </ul>
          </n-alert>
          <p
            v-if="importPreview.questions.length"
            class="import-summary"
          >
            {{ t('learning.test.import.willCreate', { count: importPreview.questions.length }) }}
          </p>
          <ul class="import-list">
            <li
              v-for="q in importPreview.questions"
              :key="q.row"
            >
              <span class="import-row">#{{ q.row }}</span>
              <span class="import-text">{{ q.text }}</span>
              <n-tag
                size="tiny"
                :bordered="false"
                :type="q.multi ? 'info' : 'default'"
              >
                {{ q.multi ? t('learning.test.multi') : t('learning.test.single') }}
              </n-tag>
            </li>
          </ul>
          <n-empty
            v-if="!importPreview.questions.length && !importPreview.errors.length"
            :description="t('learning.test.import.emptyFile')"
          />
        </template>
        <template #footer>
          <div class="modal-actions">
            <n-button @click="importPreviewOpen = false">
              {{ t('common.cancel') }}
            </n-button>
            <n-button
              type="primary"
              :disabled="!importPreview || importPreview.questions.length === 0"
              :loading="importMut.isPending.value"
              @click="confirmImport"
            >
              {{ t('learning.test.import.confirm') }}
            </n-button>
          </div>
        </template>
      </n-modal>
    </n-drawer-content>
  </n-drawer>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NAlert,
  NButton,
  NDivider,
  NDrawer,
  NDrawerContent,
  NEmpty,
  NForm,
  NFormItem,
  NIcon,
  NInputNumber,
  NModal,
  NPopconfirm,
  NSpin,
  NSwitch,
  NTag,
  NText,
  useMessage,
} from 'naive-ui'
import { AddOutline } from '@vicons/ionicons5'
import {
  useAdminTestQuery,
  useDeleteQuestionMutation,
  useImportQuestionsMutation,
  usePreviewQuestionsImportMutation,
  useUpdateTestSettingsMutation,
} from '../../queries/learning'
import { downloadQuestionsTemplate } from '../../api/learning'
import { downloadBlob } from '../../utils/download'
import type { LearningQuestionOut, QuestionsImportPreview } from '../../api/learning'
import { parseApiError } from '../../utils/parseApiError'
import QuestionFormModal from './QuestionFormModal.vue'

const props = defineProps<{ show: boolean; itemId: string | null }>()
const emit = defineEmits<{ (e: 'update:show', value: boolean): void }>()

const { t } = useI18n()
const message = useMessage()

const query = useAdminTestQuery(computed(() => (props.show ? props.itemId : null)))
const config = computed(() => query.data.value ?? null)

const drawerWidth = computed(() => Math.min(window.innerWidth - 48, 720))

const settings = reactive({
  passScore: 70,
  maxAttempts: 3,
  timeLimit: null as number | null,
  shuffleQuestions: false,
  shuffleAnswers: false,
})

watch(
  () => query.data.value,
  (c) => {
    if (c) {
      settings.passScore = c.pass_score
      settings.maxAttempts = c.max_attempts
      settings.timeLimit = c.time_limit_minutes ?? null
      settings.shuffleQuestions = c.shuffle_questions
      settings.shuffleAnswers = c.shuffle_answers
    }
  },
  { immediate: true },
)
watch(() => query.error.value, (e) => { if (e) message.error(parseApiError(e, t)) })

const settingsMut = useUpdateTestSettingsMutation()
const deleteMut = useDeleteQuestionMutation()
watch(() => settingsMut.error.value, (e) => { if (e) message.error(parseApiError(e, t)) })
watch(() => deleteMut.error.value, (e) => { if (e) message.error(parseApiError(e, t)) })

async function saveSettings() {
  if (!props.itemId) return
  try {
    await settingsMut.mutateAsync({
      itemId: props.itemId,
      body: {
        pass_score: settings.passScore,
        max_attempts: settings.maxAttempts,
        // всегда отправляем: null = снять ограничение (сервер понимает
        // явный null как «снять», см. model_fields_set в роутере)
        time_limit_minutes: settings.timeLimit,
        shuffle_questions: settings.shuffleQuestions,
        shuffle_answers: settings.shuffleAnswers,
      },
    })
    message.success(t('common.saved'))
  } catch {
    // ошибка уже показана в watch
  }
}

const formOpen = ref(false)
const editingQuestion = ref<LearningQuestionOut | null>(null)

function openAdd() {
  editingQuestion.value = null
  formOpen.value = true
}

function openEdit(q: LearningQuestionOut) {
  editingQuestion.value = q
  formOpen.value = true
}

async function removeQuestion(questionId: string) {
  if (!props.itemId) return
  try {
    await deleteMut.mutateAsync({ itemId: props.itemId, questionId })
  } catch {
    // ошибка уже показана в watch
  }
}

// ── импорт вопросов из xlsx (этап 2, ТЗ §13/§15) ─────────────────────────────
const importFileInput = ref<HTMLInputElement | null>(null)
const importFile = ref<File | null>(null)
const importPreviewOpen = ref(false)
const importPreview = ref<QuestionsImportPreview | null>(null)
const previewMut = usePreviewQuestionsImportMutation()
const importMut = useImportQuestionsMutation()

watch(() => previewMut.error.value, (e) => { if (e) message.error(parseApiError(e, t)) })
watch(() => importMut.error.value, (e) => { if (e) message.error(parseApiError(e, t)) })

function pickImportFile() {
  importFileInput.value?.click()
}

async function onImportFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file || !props.itemId) return
  importFile.value = file
  try {
    importPreview.value = await previewMut.mutateAsync({ itemId: props.itemId, file })
    importPreviewOpen.value = true
  } catch {
    // ошибка уже показана в watch
  }
}

async function confirmImport() {
  if (!props.itemId || !importFile.value) return
  try {
    const result = await importMut.mutateAsync({ itemId: props.itemId, file: importFile.value })
    message.success(
      t('learning.test.import.done', { created: result.created, errors: result.errors.length }),
    )
    importPreviewOpen.value = false
    importFile.value = null
  } catch {
    // ошибка уже показана в watch
  }
}

async function downloadTemplate() {
  if (!props.itemId) return
  try {
    const blob = await downloadQuestionsTemplate(props.itemId)
    downloadBlob(blob, 'learning-questions-template.xlsx')
  } catch (e) {
    message.error(parseApiError(e, t))
  }
}
</script>

<style scoped>
.settings-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.questions-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.head-buttons {
  display: flex;
  align-items: center;
  gap: 6px;
}

.import-input {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
}

.import-errors {
  margin-bottom: 12px;
}

.import-errors__title {
  margin: 0 0 6px;
  font-weight: 600;
}

.import-errors__list {
  margin: 0;
  padding-left: 18px;
}

.import-summary {
  margin: 0 0 8px;
  font-weight: 500;
}

.import-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 320px;
  overflow: auto;
}

.import-row {
  color: var(--text-secondary, #999);
  font-size: 12px;
  width: 40px;
  display: inline-block;
}

.import-text {
  flex: 1;
  margin-right: 8px;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.section-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}

.questions-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.question-card {
  border: 1px solid rgba(128, 128, 128, 0.2);
  border-radius: 10px;
  padding: 10px 12px;
}

.question-head {
  display: flex;
  align-items: baseline;
  gap: 6px;
}

.question-text {
  font-weight: 500;
  flex: 1;
}

.options-list {
  margin: 8px 0;
  padding-left: 20px;
}

.options-list li.correct {
  color: #18a058;
  font-weight: 500;
}

.question-actions {
  display: flex;
  gap: 6px;
}
</style>
