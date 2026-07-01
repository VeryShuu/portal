<template>
  <div class="ticket-reply">
    <n-input
      v-model:value="body"
      type="textarea"
      :autosize="{ minRows: 3, maxRows: 8 }"
      :placeholder="t('helpdesk.replyPlaceholder')"
      :disabled="loading"
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
        :disabled="!body.trim()"
        @click="onSubmit"
      >
        {{ t('helpdesk.replySend') }}
      </n-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { NInput, NButton, NUpload, NIcon, NRadioGroup, NRadioButton } from 'naive-ui'
import { AttachOutline } from '@vicons/ionicons5'
import type { UploadFileInfo } from 'naive-ui'

const props = defineProps<{
  /** Агентский режим: показывает переключатель public/internal. */
  agentMode?: boolean
  loading?: boolean
}>()

const emit = defineEmits<{
  submit: [payload: { body: string; visibility: 'public' | 'internal'; files: File[] }]
}>()

const { t } = useI18n()
const body = ref('')
const visibility = ref<'public' | 'internal'>('public')
const fileList = ref<UploadFileInfo[]>([])

function onSubmit() {
  const text = body.value.trim()
  if (!text) return
  const files = (fileList.value ?? [])
    .map((f) => f.file)
    .filter((f): f is File => !!f)
  emit('submit', { body: text, visibility: visibility.value, files })
  // Сброс после отправки (родитель управляет loading; успех — очистка).
  body.value = ''
  fileList.value = []
}

defineExpose({
  props,
})
</script>

<style scoped>
.ticket-reply {
  display: flex;
  flex-direction: column;
  gap: 12px;
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
