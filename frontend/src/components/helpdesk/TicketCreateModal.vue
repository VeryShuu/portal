<template>
  <n-modal
    :show="show"
    preset="card"
    :title="t('helpdesk.createTitle')"
    style="max-width: 560px"
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
          v-model:value="form.subject"
          :placeholder="t('helpdesk.subjectPlaceholder')"
          :maxlength="500"
          :disabled="loading"
        />
      </n-form-item>
      <n-form-item
        :label="t('helpdesk.description')"
        style="margin-bottom: 12px"
      >
        <n-input
          v-model:value="form.description"
          type="textarea"
          :autosize="{ minRows: 4, maxRows: 10 }"
          :placeholder="t('helpdesk.descriptionPlaceholder')"
          :disabled="loading"
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
          :disabled="!form.subject.trim() || !form.description.trim()"
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
import { useCreateMyTicketMutation } from '../../queries/helpdesk'
import { parseApiError } from '../../utils/parseApiError'

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{
  'update:show': [v: boolean]
  created: []
}>()

const { t } = useI18n()
const message = useMessage()
const mut = useCreateMyTicketMutation()

const form = ref({ subject: '', description: '' })
const fileList = ref<UploadFileInfo[]>([])
const loading = ref(false)

// Сброс формы при открытии.
watch(
  () => props.show,
  (v) => {
    if (v) {
      form.value = { subject: '', description: '' }
      fileList.value = []
    }
  },
)

async function onSubmit() {
  const subject = form.value.subject.trim()
  const description = form.value.description.trim()
  if (!subject || !description) return
  const files = (fileList.value ?? []).map((f) => f.file).filter((f): f is File => !!f)
  loading.value = true
  try {
    await mut.mutateAsync({ dto: { subject, description }, files })
    message.success(t('helpdesk.createSuccess'))
    emit('update:show', false)
    emit('created')
  } catch (e) {
    message.error(parseApiError(e, () => t('errors.generic')))
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
</style>
