<template>
  <div class="form-card form-card--sticky">
    <div class="side-title">
      {{ t('news.form.coverImage') }}
    </div>

    <NewsCoverUpload
      v-model:cover-image-url="coverImageUrl"
      v-model:focal-x="focalX"
      v-model:focal-y="focalY"
      v-model:focal-zoom="focalZoom"
      :news-id="newsId"
      :is-edit="isEdit"
      :max-size-mb="coverMaxSizeMb"
    />

    <div class="side-divider" />

    <div class="side-title">
      {{ t('news.form.settings') }}
    </div>
    <div class="side-hint">
      {{ t('news.form.settingsHint') }}
    </div>

    <n-form-item :label="t('news.form.status')">
      <n-select
        v-model:value="status"
        :options="statusOptions"
      />
    </n-form-item>

    <n-form-item :label="t('news.form.categories')">
      <n-select
        v-model:value="categories"
        :options="categoryOptions"
        :placeholder="t('news.form.categoriesPlaceholder')"
        multiple
        clearable
        filterable
        tag
      />
    </n-form-item>

    <n-form-item>
      <n-checkbox v-model:checked="isPinned">
        <n-icon
          class="pin-icon"
          size="14"
        >
          <StarOutline />
        </n-icon>
        {{ t('news.pinned') }}
      </n-checkbox>
    </n-form-item>

    <n-form-item :label="t('news.create.scheduleAt')">
      <n-date-picker
        v-model:value="publishAtMs"
        type="datetime"
        clearable
        style="width:100%"
      />
    </n-form-item>

    <n-form-item :label="t('news.form.publishedAt')">
      <n-date-picker
        v-model:value="publishedAtMs"
        type="datetime"
        clearable
        style="width:100%"
      />
    </n-form-item>

    <div class="side-actions">
      <n-button
        block
        :loading="saving"
        @click="$emit('save-draft')"
      >
        {{ t('news.create.saveDraft') }}
      </n-button>
      <n-button
        block
        type="primary"
        :loading="saving"
        @click="$emit('publish')"
      >
        {{ t('news.create.submit') }}
      </n-button>
      <n-button
        text
        block
        @click="$emit('cancel')"
      >
        {{ t('common.cancel') }}
      </n-button>
    </div>

    <div
      v-if="lastSaved"
      class="autosave-hint"
    >
      <n-icon size="13">
        <CheckmarkCircleOutline />
      </n-icon>
      {{ t('news.form.autosaved', { time: lastSaved }) }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NFormItem, NSelect, NCheckbox, NDatePicker, NButton, NIcon, type SelectOption } from 'naive-ui'
import { StarOutline, CheckmarkCircleOutline } from '@vicons/ionicons5'
import NewsCoverUpload from './NewsCoverUpload.vue'
import type { NewsStatus } from '../../pages/composables/newsFormMappers'

defineProps<{
  newsId?: string
  isEdit: boolean
  coverMaxSizeMb: number
  statusOptions: SelectOption[]
  categoryOptions: SelectOption[]
  saving: boolean
  lastSaved: string
}>()

defineEmits<{
  'save-draft': []
  'publish': []
  'cancel': []
}>()

const coverImageUrl = defineModel<string | null>('coverImageUrl', { required: true })
const focalX = defineModel<number | null>('focalX', { required: true })
const focalY = defineModel<number | null>('focalY', { required: true })
const focalZoom = defineModel<number | null>('focalZoom', { required: true })
const status = defineModel<NewsStatus>('status', { required: true })
const categories = defineModel<string[]>('categories', { required: true })
const isPinned = defineModel<boolean>('isPinned', { required: true })
const publishAtMs = defineModel<number | null>('publishAtMs', { required: true })
const publishedAtMs = defineModel<number | null>('publishedAtMs', { required: true })

const { t } = useI18n()
</script>

<style scoped>
.form-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 20px 22px;
  box-shadow: var(--shadow-sm);
  transition: border-color 0.15s, box-shadow 0.15s;
}
.form-card--sticky {
  position: sticky;
  top: 16px;
}
.side-title {
  font-size: 13px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--color-text-muted);
  margin-bottom: 4px;
}
.side-hint {
  font-size: 12px;
  color: var(--color-text-subtle);
  margin-bottom: 16px;
  line-height: 1.5;
}
.side-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 8px;
  padding-top: 14px;
  border-top: 1px solid var(--color-border);
}
.pin-icon {
  color: var(--color-brand-red);
  margin-right: 2px;
  vertical-align: -2px;
}
.autosave-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  justify-content: center;
  margin-top: 12px;
  font-size: 12px;
  color: var(--color-success);
}
.side-divider {
  height: 1px;
  background: var(--color-border);
  margin: 16px 0;
}
@media (max-width: 1100px) {
  .form-card--sticky { position: static; }
}
</style>
