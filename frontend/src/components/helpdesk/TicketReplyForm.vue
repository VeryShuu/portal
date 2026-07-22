<template>
  <div class="ticket-reply">
    <RichEditor
      v-model="markdown"
      :placeholder="t('helpdesk.replyPlaceholder')"
      :upload-endpoint="uploadEndpoint"
      class="ticket-reply__editor"
    />
    <div
      v-if="agentMode && participants.length > 0"
      class="ticket-reply__cc-row"
    >
      <n-checkbox
        v-model:checked="replyAll"
        :disabled="loading"
        size="small"
      >
        {{ t('helpdesk.replyAll') }}
      </n-checkbox>
      <n-select
        v-if="replyAll"
        v-model:value="ccEmails"
        multiple
        filterable
        tag
        :options="ccOptions"
        :placeholder="t('helpdesk.ccPlaceholder')"
        :max-tag-count="5"
        size="small"
        class="ticket-reply__cc-select"
        :disabled="loading"
      />
    </div>
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
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NUpload, NIcon, NRadioGroup, NRadioButton, NCheckbox, NSelect } from 'naive-ui'
import { AttachOutline } from '@vicons/ionicons5'
import type { UploadFileInfo } from 'naive-ui'
import RichEditor from '../RichEditor.vue'
import { mdUnsafe as md } from '../../utils/markdown'
import type { HelpdeskParticipant } from '../../api/helpdesk'

const props = defineProps<{
  /** Агентский режим: показывает переключатель public/internal. */
  agentMode?: boolean
  loading?: boolean
  /** ID тикета — для upload-endpoint inline-картинок rich-редактора. */
  ticketId: string
  /** Участники тикета (requester + Cc + авторы сообщений). Источник для
   *  pre-fill чекбокса «Ответить всем» (миграция 083). Только агентский view. */
  participants?: HelpdeskParticipant[]
}>()

const emit = defineEmits<{
  /** body_html — отрендеренный из markdown (TipTap) HTML; plain бэк деривит сам.
   *  cc — список email'ов в копии (только при включённом «Ответить всем»). */
  submit: [payload: {
    body_html: string
    visibility: 'public' | 'internal'
    files: File[]
    cc?: string[]
  }]
}>()

const { t } = useI18n()

// RichEditor (TipTap) отдаёт markdown через tiptap-markdown. Храним его, а на
// submit рендерим в HTML (markdown-it, как в news/kb) — бэк хранит только HTML.
const markdown = ref('')
const visibility = ref<'public' | 'internal'>('public')
const fileList = ref<UploadFileInfo[]>([])

// «Ответить всем» (миграция 083): чекбокс раскрывает редактируемый список Cc.
// По умолчанию выключен — чтобы агент осознанно подтвердил получателей (Cc —
// attacker-controlled из inbound email; отправка только по явному действию).
const replyAll = ref(false)
// Список email'ов в копии. Изначально pre-fill из участников тикета (минус
// requester — он в To; support_address/агента выкинет бэк на нормализации).
// ``tag`` в n-select позволяет добавить произвольный email (нет в адресной книге).
const ccEmails = ref<string[]>([])

const participants = computed(() => props.participants ?? [])

// Опции для n-select: участники тикета (кроме requester — он уже в To).
const ccOptions = computed(() =>
  participants.value
    .filter((p) => !p.is_requester)
    .map((p) => ({
      label: p.name ? `${p.name} (${p.email})` : p.email,
      value: p.email,
    })),
)

// При включении чекбокса — pre-fill из участников (минус requester). При
// выключении — очистка (на случай повторного включения берём свежий список).
watch(replyAll, (on) => {
  if (on) {
    ccEmails.value = participants.value
      .filter((p) => !p.is_requester)
      .map((p) => p.email)
  } else {
    ccEmails.value = []
  }
})

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
  // Cc передаём только при включённом чекбоксе (иначе undefined — бэк не
  // получит поле ``cc`` в FormData, создаст ответ без копии).
  const cc = replyAll.value && ccEmails.value.length > 0 ? ccEmails.value : undefined
  emit('submit', { body_html: bodyHtml, visibility: visibility.value, files, cc })
  // Сброс после отправки (родитель управляет loading; успех — очистка).
  markdown.value = ''
  fileList.value = []
  replyAll.value = false
  ccEmails.value = []
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
/* «Ответить всем» (миграция 083): чекбокс + редактируемый список Cc. */
.ticket-reply__cc-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.ticket-reply__cc-select {
  flex: 1;
  min-width: 240px;
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
