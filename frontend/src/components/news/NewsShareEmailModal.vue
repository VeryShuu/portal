<template>
  <n-modal
    :show="show"
    preset="card"
    :title="t('news.share.title')"
    style="width:540px;max-width:94vw"
    :mask-closable="false"
    @update:show="(v: boolean) => emit('update:show', v)"
  >
    <n-form label-placement="top">
      <n-form-item
        :label="t('news.share.recipientsLabel')"
        :feedback="recipientsError"
        :validation-status="recipientsError ? 'error' : undefined"
      >
        <n-select
          v-model:value="selectedIds"
          multiple
          filterable
          :options="recipientOptions"
          :loading="loadingRecipients"
          :placeholder="t('news.share.recipientsPlaceholder')"
          :max-tag-count="4"
        />
      </n-form-item>

      <div
        v-if="!loadingRecipients && recipientOptions.length === 0"
        class="share-empty-hint"
      >
        {{ t('news.share.noRecipients') }}
      </div>

      <n-form-item :label="t('news.share.messageLabel')">
        <n-input
          v-model:value="messageText"
          type="textarea"
          :autosize="{ minRows: 4, maxRows: 10 }"
          :maxlength="2000"
          show-count
          :placeholder="t('news.share.messagePlaceholder')"
        />
      </n-form-item>
    </n-form>

    <template #footer>
      <div class="modal-footer">
        <n-button @click="emit('update:show', false)">
          {{ t('common.cancel') }}
        </n-button>
        <n-button
          type="primary"
          :loading="sending"
          :disabled="selectedIds.length === 0"
          @click="submit"
        >
          {{ t('news.share.send') }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NModal, NForm, NFormItem, NSelect, NInput, NButton, useMessage } from 'naive-ui'
import { useMailingRecipientsQuery } from '../../queries/mailingRecipients'
import { useShareNewsEmailMutation } from '../../queries/news'
import { parseApiError } from '../../utils/parseApiError'

const props = defineProps<{
  show: boolean
  newsId: string
  newsTitle: string
  newsBody: string
}>()

const emit = defineEmits<{ 'update:show': [value: boolean] }>()

const { t } = useI18n()
const notify = useMessage()

const enabled = computed(() => props.show)
const { data: recipientsData, isLoading: loadingRecipients } = useMailingRecipientsQuery(
  { limit: 500 },
  { enabled },
)

const recipientOptions = computed(() =>
  (recipientsData.value?.items ?? []).map((r) => ({
    label: r.label ? `${r.name} <${r.email}> · ${r.label}` : `${r.name} <${r.email}>`,
    value: r.id,
  })),
)

const selectedIds = ref<string[]>([])
const messageText = ref('')
const recipientsError = ref('')

function buildExcerpt(body: string, limit = 300): string {
  let text = body || ''
  text = text.replace(/```[\s\S]*?```/g, ' ')
  text = text.replace(/!\[[^\]]*\]\([^)]*\)/g, ' ')
  text = text.replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
  text = text.replace(/[`*_~>#]+/g, '')
  text = text.replace(/\s+/g, ' ').trim()
  if (text.length > limit) text = text.slice(0, limit).trimEnd() + '…'
  return text
}

watch(
  () => props.show,
  (open) => {
    if (open) {
      selectedIds.value = []
      messageText.value = buildExcerpt(props.newsBody)
      recipientsError.value = ''
    }
  },
)

const shareMutation = useShareNewsEmailMutation()
const sending = computed(() => shareMutation.isPending.value)

async function submit() {
  recipientsError.value = ''
  if (selectedIds.value.length === 0) {
    recipientsError.value = t('news.share.recipientsRequired')
    return
  }
  try {
    const res = await shareMutation.mutateAsync({
      newsId: props.newsId,
      dto: {
        recipient_ids: selectedIds.value,
        message: messageText.value.trim() || null,
      },
    })
    notify.success(t('news.share.success', { count: res.enqueued }))
    emit('update:show', false)
  } catch (err: unknown) {
    const status = (err as { response?: { status?: number } })?.response?.status
    if (status === 409) {
      notify.error(t('news.share.notPublished'))
    } else {
      notify.error(parseApiError(err, t))
    }
  }
}
</script>

<style scoped>
.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.share-empty-hint {
  margin: -4px 0 12px;
  font-size: 13px;
  color: var(--color-text-muted);
}
</style>
