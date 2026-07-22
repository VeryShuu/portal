<template>
  <n-modal
    :show="show"
    preset="card"
    :title="t('helpdesk.createTitle')"
    style="max-width: 720px"
    @update:show="(v: boolean) => !v && emit('update:show', false)"
  >
    <n-form
      ref="formRef"
      label-placement="top"
      :show-feedback="false"
    >
      <n-form-item
        :label="t('helpdesk.subject')"
        style="margin-bottom: 12px"
      >
        <n-input
          v-model:value="subject"
          :placeholder="t('helpdesk.subjectPlaceholder')"
          :maxlength="500"
          :disabled="loading"
        />
      </n-form-item>
      <n-form-item
        :label="t('helpdesk.description')"
        style="margin-bottom: 12px"
      >
        <!--
          RichEditor (TipTap) — симметрично TicketReplyForm. Inline-картинки
          грузятся через ``POST /draft-attachments`` (нет ticket_id до сохранения,
          см. backend ``services/helpdesk/drafts.py``): фронт получает draft-URL,
          вставляет его в markdown, на submit рендерит HTML. Бэкенд при
          ``create_ticket`` переносит draft-файлы в ``TKT-{number}/inline/`` и
          переписывает ``src`` на постоянный inline-media URL (backfill).
          md-render в HTML на submit делает фронт (бэк повторно sanitize nh3).
        -->
        <RichEditor
          v-model="markdown"
          :upload-endpoint="uploadEndpoint"
          :placeholder="t('helpdesk.descriptionPlaceholder')"
          class="create-modal__editor"
        />
      </n-form-item>
      <n-upload
        v-model:file-list="fileList"
        :max="10"
        multiple
        :default-upload="false"
        :disabled="loading"
      >
        <n-button
          quaternary
          :disabled="loading"
        >
          <template #icon>
            <n-icon><component :is="AttachOutline" /></n-icon>
          </template>
          {{ t('helpdesk.attachFiles') }}
        </n-button>
      </n-upload>
    </n-form>

    <template #footer>
      <div class="modal-actions">
        <n-button
          :disabled="loading"
          @click="emit('update:show', false)"
        >
          {{ t('common.cancel') }}
        </n-button>
        <n-button
          type="primary"
          :loading="loading"
          :disabled="!subject.trim() || !markdown.trim()"
          @click="onSubmit"
        >
          {{ t('helpdesk.createSubmit') }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NModal, NForm, NFormItem, NInput, NButton, NUpload, NIcon, useMessage } from 'naive-ui'
import { AttachOutline } from '@vicons/ionicons5'
import type { UploadFileInfo } from 'naive-ui'
import RichEditor from '../RichEditor.vue'
import { useCreateMyTicketMutation } from '../../queries/helpdesk'
import { parseApiError } from '../../utils/parseApiError'
import { mdUnsafe as md } from '../../utils/markdown'

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{
  'update:show': [v: boolean]
  created: []
}>()

const { t } = useI18n()
const message = useMessage()
const mut = useCreateMyTicketMutation()

// Draft-attachments endpoint: inline-картинки в форме создания заявки (нет
// ticket_id до сохранения). Бэкенд backfill'ит draft-URL при create_ticket.
const uploadEndpoint = '/api/v1/helpdesk/draft-attachments'
const subject = ref('')
// RichEditor (TipTap) отдаёт markdown через tiptap-markdown. На submit рендерим
// в HTML (markdown-it, как в TicketReplyForm/news/kb) — бэк хранит только HTML.
const markdown = ref('')
const fileList = ref<UploadFileInfo[]>([])
const loading = ref(false)

// Сброс формы при открытии.
watch(
  () => props.show,
  (v) => {
    if (v) {
      subject.value = ''
      markdown.value = ''
      fileList.value = []
    }
  },
)

async function onSubmit() {
  const subjectVal = subject.value.trim()
  const mdSrc = markdown.value.trim()
  if (!subjectVal || !mdSrc) return
  const descriptionHtml = md.render(mdSrc)
  const files = (fileList.value ?? []).map((f) => f.file).filter((f): f is File => !!f)
  loading.value = true
  try {
    await mut.mutateAsync({
      dto: { subject: subjectVal, description: mdSrc, description_html: descriptionHtml },
      files,
    })
    message.success(t('helpdesk.createSuccess'))
    emit('update:show', false)
    emit('created')
  } catch (e) {
    message.error(parseApiError(e, t))
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}
.create-modal__editor {
  width: 100%;
}
</style>
