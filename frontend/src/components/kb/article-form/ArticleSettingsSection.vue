<template>
  <section class="settings-card">
    <h2 class="settings-card__title">
      {{ t('kb.form.settings') }}
    </h2>

    <n-form-item :label="t('kb.form.status')">
      <n-select
        :value="status"
        :options="statusOptions"
        @update:value="$emit('update:status', $event)"
      />
    </n-form-item>

    <n-form-item :label="t('kb.form.section')">
      <n-tree-select
        :value="sectionId"
        :options="sectionOptions"
        :placeholder="t('kb.form.sectionPlaceholder')"
        clearable
        @update:value="$emit('update:sectionId', $event)"
      />
    </n-form-item>

    <n-form-item :label="t('kb.form.tags')">
      <n-dynamic-tags
        :value="tags"
        @update:value="$emit('update:tags', $event)"
      />
    </n-form-item>

    <n-form-item
      v-if="isEdit"
      :label="t('kb.form.changeComment')"
    >
      <n-input
        :value="changeComment"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 4 }"
        :placeholder="t('kb.form.changeCommentPlaceholder')"
        @update:value="$emit('update:changeComment', $event)"
      />
    </n-form-item>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NFormItem, NSelect, NTreeSelect, NDynamicTags, NInput, type SelectOption } from 'naive-ui'

interface SectionOption {
  label: string
  key: string
  children?: SectionOption[]
  [k: string]: unknown
}

defineProps<{
  status: 'draft' | 'published'
  sectionId: string | null
  tags: string[]
  changeComment: string
  isEdit: boolean
  statusOptions: SelectOption[]
  sectionOptions: SectionOption[]
}>()

defineEmits<{
  'update:status': [value: 'draft' | 'published']
  'update:sectionId': [value: string | null]
  'update:tags': [value: string[]]
  'update:changeComment': [value: string]
}>()

const { t } = useI18n()
</script>

<style scoped>
.settings-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 18px 18px 6px;
  box-shadow: var(--shadow-sm);
}

.settings-card__title {
  margin: 0 0 14px;
  font-size: 14px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--color-text-subtle);
}
</style>
