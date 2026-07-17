<template>
  <div class="ticket-reply">
    <RichEditor
      v-model="markdown"
      :placeholder="t('helpdesk.replyPlaceholder')"
      :upload-endpoint="uploadEndpoint"
      class="ticket-reply__editor"
    />
    <div class="ticket-reply__actions">
      <div class="ticket-reply__left">
        <n-upload
          v-model:file-list="fileList"
          :max="10"
          multiple
          :default-upload="false"
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
        <n-radio-group
          v-if="agentMode"
          v-model:value="visibility"
          size="small"
          class="ticket-reply__visibility"
        >
          <n-radio-button value="public">
            {{ t('helpdesk.visibilityPublic') }}
          </n-radio-button>
          <n-radio-button value="internal">
            {{ t('helpdesk.visibilityInternal') }}
          </n-radio-button>
        </n-radio-group>
      </div>
      <n-button
        type="primary"
        :loading="loading"
        :disabled="!canSubmit"
        @click="onSubmit"
      >
        {{ t('helpdesk.replySend') }}
      </n-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NUpload, NIcon, NRadioGroup, NRadioButton } from 'naive-ui'
import { AttachOutline } from '@vicons/ionicons5'
import type { UploadFileInfo } from 'naive-ui'
import RichEditor from '../RichEditor.vue'
import { mdUnsafe as md } from '../../utils/markdown'

const props = defineProps<{
  /** Агентский режим: показывает переключатель public/internal. */
  agentMode?: boolean
  loading?: boolean
  /** ID тикета — для upload-endpoint inline-картинок rich-редактора. */
  ticketId: string
}>()

const emit = defineEmits<{
  /** body_html — отрендеренный из markdown (TipTap) HTML; plain бэк деривит сам. */
  submit: [payload: { body_html: string; visibility: 'public' | 'internal'; files: File[] }]
}>()

const { t } = useI18n()

// RichEditor (TipTap) отдаёт markdown через tiptap-markdown. Храним его, а на
// submit рендерим в HTML (markdown-it, как в news/kb) — бэк хранит только HTML.
const markdown = ref('')
const visibility = ref<'public' | 'internal'>('public')
const fileList = ref<UploadFileInfo[]>([])

// Upload-endpoint для inline-картинок: зависит от ticketId (передаётся родителем).
const uploadEndpoint = computed(
  () => `/api/v1/helpdesk/tickets/${props.ticketId}/inline-media`,
)

const canSubmit = computed(() => markdown.value.trim().length > 0)

function onSubmit() {
  const mdSrc = markdown.value.trim()
  if (!mdSrc) return
  // markdown → HTML (как в KB/news через mdUnsafe). Бэк повторно sanitize'ит
  // (nh3) при записи — двойная защита, т.к. заявитель неконтролируемая сторона.
  const bodyHtml = md.render(mdSrc)
  const files = (fileList.value ?? [])
    .map((f) => f.file)
    .filter((f): f is File => !!f)
  emit('submit', { body_html: bodyHtml, visibility: visibility.value, files })
  // Сброс после отправки (родитель управляет loading; успех — очистка).
  markdown.value = ''
  fileList.value = []
}
</script>

<style scoped>
.ticket-reply {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.ticket-reply__editor {
  width: 100%;
}
.ticket-reply__actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.ticket-reply__left {
  display: flex;
  align-items: center;
  gap: 16px;
}
.ticket-reply__visibility {
  margin-left: 8px;
}
</style>
