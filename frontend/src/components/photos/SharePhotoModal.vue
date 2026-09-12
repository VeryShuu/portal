<template>
  <n-modal
    :show="show"
    preset="card"
    :title="t('photos.lightbox.createShareLink')"
    style="width:520px;max-width:94vw"
    @update:show="onUpdateShow"
  >
    <n-form>
      <n-form-item :label="t('photos.lightbox.expiresIn')">
        <n-select
          :value="expiresInDays"
          :options="expiryOptions"
          @update:value="onUpdateExpires"
        />
      </n-form-item>
      <div
        v-if="shareUrl"
        class="share-result"
      >
        <n-input
          :value="shareUrl"
          readonly
        />
        <n-button
          size="small"
          @click="$emit('copy')"
        >
          {{ t('common.copy') }}
        </n-button>
      </div>
      <div class="share-actions">
        <n-button @click="onUpdateShow(false)">
          {{ t('common.close') }}
        </n-button>
        <n-button
          type="primary"
          :loading="creating"
          @click="$emit('generate')"
        >
          {{ t('photos.lightbox.generate') }}
        </n-button>
      </div>
    </n-form>
  </n-modal>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NButton, NForm, NFormItem, NInput, NModal, NSelect, type SelectOption } from 'naive-ui'

defineProps<{
  show: boolean
  expiresInDays: number | null
  shareUrl: string
  creating: boolean
  expiryOptions: SelectOption[]
}>()

const emit = defineEmits<{
  (e: 'update:show', val: boolean): void
  (e: 'update:expiresInDays', val: number | null): void
  (e: 'generate'): void
  (e: 'copy'): void
}>()

const { t } = useI18n()

function onUpdateShow(val: boolean) {
  emit('update:show', val)
}

function onUpdateExpires(val: number | null) {
  emit('update:expiresInDays', val)
}
</script>

<style scoped>
.share-result { display: flex; gap: 8px; align-items: center; margin: 12px 0; }
.share-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 12px; }
</style>
