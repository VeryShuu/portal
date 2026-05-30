<template>
  <n-gi :span="2">
    <n-form-item
      :label="t('kb.form.title')"
      required
    >
      <n-input
        :value="title"
        :placeholder="t('kb.form.titlePlaceholder')"
        size="large"
        style="font-size:20px;font-weight:700"
        @update:value="$emit('update:title', $event)"
      />
    </n-form-item>
  </n-gi>

  <n-gi>
    <n-form-item :label="t('kb.form.section')">
      <n-tree-select
        :value="sectionId"
        :options="sectionOptions"
        :placeholder="t('kb.form.sectionPlaceholder')"
        clearable
        style="width:100%"
        @update:value="$emit('update:sectionId', $event)"
      />
    </n-form-item>
  </n-gi>

  <n-gi :span="2">
    <n-form-item :label="t('kb.form.tags')">
      <n-dynamic-tags
        :value="tags"
        @update:value="$emit('update:tags', $event)"
      />
    </n-form-item>
  </n-gi>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NFormItem, NInput, NTreeSelect, NDynamicTags, NGi } from 'naive-ui'

interface SectionOption {
  label: string
  key: string
  children?: SectionOption[]
  [k: string]: unknown
}

defineProps<{
  title: string
  sectionId: string | null
  tags: string[]
  sectionOptions: SectionOption[]
}>()

defineEmits<{
  'update:title': [value: string]
  'update:sectionId': [value: string | null]
  'update:tags': [value: string[]]
}>()

const { t } = useI18n()
</script>
