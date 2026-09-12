<template>
  <button
    v-if="showButton"
    type="button"
    class="fb-fab"
    :title="t('feedback.button')"
    :aria-label="t('feedback.button')"
    @click="open"
  >
    <n-icon size="20">
      <ChatbubbleEllipsesOutline />
    </n-icon>
    <span class="fb-fab__label">{{ t('feedback.button') }}</span>
  </button>

  <n-modal
    v-model:show="show"
    preset="card"
    :title="t('feedback.modalTitle')"
    style="width:560px;max-width:94vw"
    :mask-closable="!submitting"
  >
    <n-form
      :model="form"
      label-placement="top"
      @submit.prevent="submit"
    >
      <n-form-item
        :label="t('feedback.categoryLabel')"
        path="category"
      >
        <n-select
          v-model:value="form.category"
          :options="categoryOptions"
        />
      </n-form-item>
      <n-form-item
        :label="t('feedback.messageLabel')"
        path="message"
      >
        <n-input
          v-model:value="form.message"
          type="textarea"
          :rows="5"
          :placeholder="t('feedback.messagePlaceholder')"
          :maxlength="5000"
          show-count
        />
      </n-form-item>
      <n-form-item :label="t('feedback.attachmentsLabel')">
        <div class="fb-att">
          <input
            ref="fileInputRef"
            type="file"
            multiple
            :accept="FEEDBACK_ATTACHMENT_ACCEPT"
            class="fb-att__input"
            :aria-label="t('feedback.attachmentsLabel')"
            @change="onFilesPicked"
            @paste.stop
          >
          <n-button
            size="small"
            :disabled="submitting || files.length >= FEEDBACK_ATTACHMENT_MAX_PER_TICKET"
            @click="pickFiles"
          >
            <template #icon>
              <n-icon><AttachOutline /></n-icon>
            </template>
            {{ t('feedback.attachFiles') }}
          </n-button>
          <span class="fb-att__hint">
            {{ t('feedback.attachmentsHint', { max: FEEDBACK_ATTACHMENT_MAX_PER_TICKET, sizeMb: 10 }) }}
          </span>
          <ul
            v-if="files.length"
            class="fb-att__list"
          >
            <li
              v-for="(f, idx) in files"
              :key="idx"
              class="fb-att__item"
            >
              <span
                class="fb-att__name"
                :title="f.name"
              >{{ f.name }}</span>
              <span class="fb-att__size">{{ formatSize(f.size) }}</span>
              <n-button
                quaternary
                size="tiny"
                :disabled="submitting"
                @click="removeFile(idx)"
              >
                <template #icon>
                  <n-icon><CloseOutline /></n-icon>
                </template>
              </n-button>
            </li>
          </ul>
        </div>
      </n-form-item>
    </n-form>
    <template #footer>
      <div style="display:flex;gap:8px;justify-content:flex-end">
        <n-button
          :disabled="submitting"
          @click="show = false"
        >
          {{ t('feedback.cancel') }}
        </n-button>
        <n-button
          type="primary"
          :loading="submitting"
          :disabled="!canSubmit"
          @click="submit"
        >
          {{ t('feedback.submit') }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import {
  NButton,
  NForm,
  NFormItem,
  NIcon,
  NInput,
  NModal,
  NSelect,
  useMessage,
} from 'naive-ui'
import { AttachOutline, ChatbubbleEllipsesOutline, CloseOutline } from '@vicons/ionicons5'
import { useAuthStore } from '../stores/auth'
import {
  createFeedback,
  uploadFeedbackAttachment,
  FEEDBACK_ATTACHMENT_ACCEPT,
  FEEDBACK_ATTACHMENT_MAX_PER_TICKET,
  FEEDBACK_ATTACHMENT_MAX_SIZE,
  type FeedbackCategory,
} from '../api/feedback'
import { parseApiError } from '../utils/parseApiError'
import { formatSize } from '@/utils/formatSize'

const { t } = useI18n()
const route = useRoute()
const auth = useAuthStore()
const message = useMessage()

const HIDDEN_ROUTES = new Set(['login', 'auth-local', 'auth-callback', 'auth-error'])

const showButton = computed(() => {
  if (!auth.isAuthenticated) return false
  const name = typeof route.name === 'string' ? route.name : null
  if (name && HIDDEN_ROUTES.has(name)) return false
  return true
})

const show = ref(false)
const submitting = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)
const files = ref<File[]>([])

const form = reactive<{ category: FeedbackCategory; message: string }>({
  category: 'bug',
  message: '',
})

function pickFiles() {
  fileInputRef.value?.click()
}

function onFilesPicked(e: Event) {
  const input = e.target as HTMLInputElement
  const picked = Array.from(input.files || [])
  for (const f of picked) {
    if (files.value.length >= FEEDBACK_ATTACHMENT_MAX_PER_TICKET) {
      message.warning(t('feedback.attachLimitReached', { max: FEEDBACK_ATTACHMENT_MAX_PER_TICKET }))
      break
    }
    if (f.size > FEEDBACK_ATTACHMENT_MAX_SIZE) {
      message.error(t('feedback.attachTooLarge', { name: f.name, sizeMb: 10 }))
      continue
    }
    files.value.push(f)
  }
  input.value = ''
}

function removeFile(idx: number) {
  files.value.splice(idx, 1)
}

const categoryOptions = computed(() => [
  { label: t('feedback.categories.bug'), value: 'bug' },
  { label: t('feedback.categories.suggestion'), value: 'suggestion' },
  { label: t('feedback.categories.other'), value: 'other' },
])

const canSubmit = computed(() => form.message.trim().length > 0 || files.value.length > 0)

function open() {
  form.category = 'bug'
  form.message = ''
  files.value = []
  show.value = true
}

function currentPageUrl(): string | null {
  if (typeof window === 'undefined') return null
  return window.location.pathname + window.location.search + window.location.hash
}

async function submit() {
  if (!canSubmit.value || submitting.value) return
  submitting.value = true
  try {
    const created = await createFeedback({
      category: form.category,
      message: form.message.trim(),
      page_url: currentPageUrl(),
    })
    let failed = 0
    for (const f of files.value) {
      try {
        await uploadFeedbackAttachment(created.id, f)
      } catch (e) {
        failed += 1
        console.error('feedback attachment upload failed', f.name, e)
      }
    }
    if (failed > 0) {
      message.warning(t('feedback.attachUploadPartial', { failed }))
    } else {
      message.success(t('feedback.successMessage'))
    }
    show.value = false
    form.message = ''
    files.value = []
  } catch (err) {
    message.error(parseApiError(err, t))
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.fb-att {
  width: 100%;
}
.fb-att__input {
  display: none;
}
.fb-att__hint {
  margin-left: 10px;
  font-size: 12px;
  color: var(--color-text-secondary, #888);
}
.fb-att__list {
  list-style: none;
  margin: 8px 0 0;
  padding: 0;
  width: 100%;
}
.fb-att__item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  border: 1px solid var(--divider-color, #eee);
  border-radius: 6px;
  margin-top: 4px;
  font-size: 13px;
}
.fb-att__name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.fb-att__size {
  color: var(--color-text-secondary, #888);
  font-size: 12px;
}
.fb-fab {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 900;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  border-radius: 999px;
  border: none;
  background: var(--primary-color, #2080f0);
  color: #fff;
  cursor: pointer;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.15);
  font-size: 14px;
  font-weight: 500;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.fb-fab:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.2);
}
.fb-fab:focus-visible {
  outline: 2px solid #fff;
  outline-offset: 2px;
}
@media (max-width: 768px) {
  .fb-fab {
    padding: 12px;
    right: 16px;
    bottom: 16px;
  }
  .fb-fab__label {
    display: none;
  }
}
</style>
