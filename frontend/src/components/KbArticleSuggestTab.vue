<template>
  <div class="suggest-form">
    <p class="suggest-form__hint">
      {{ t('kb.suggestHint') }}
    </p>
    <RichEditor
      v-model="body"
      :placeholder="t('kb.suggestPlaceholder')"
    />
    <n-input
      v-model:value="comment"
      :placeholder="t('kb.suggestCommentPlaceholder')"
      style="margin-top:8px"
    />
    <n-button
      type="primary"
      :loading="loading"
      @click="submit"
    >
      {{ t('kb.submitSuggest') }}
    </n-button>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NInput, useMessage } from 'naive-ui'
import RichEditor from './RichEditor.vue'
import { suggestEdit } from '../api/kb'

const props = defineProps<{ articleId: string }>()

const { t } = useI18n()
const message = useMessage()

const body = ref('')
const comment = ref('')
const loading = ref(false)

async function submit() {
  if (!body.value.trim()) return
  loading.value = true
  try {
    await suggestEdit(props.articleId, { body: body.value, comment: comment.value || undefined })
    body.value = ''
    comment.value = ''
    message.success(t('kb.suggestSent'))
  } catch {
    message.error(t('common.error'))
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.suggest-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.suggest-form__hint {
  margin: 0;
  font-size: 14px;
  color: var(--color-text-muted);
}
</style>
