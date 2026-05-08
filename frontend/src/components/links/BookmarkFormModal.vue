<template>
  <n-modal
    :show="show"
    preset="dialog"
    :title="t('bookmarks.add')"
    style="max-width: 480px"
    @update:show="emit('update:show', $event)"
  >
    <n-form @submit.prevent="submit" label-placement="top">
      <n-form-item :label="t('bookmarks.titleField')">
        <n-input v-model:value="title" :placeholder="t('bookmarks.titlePlaceholder')" />
      </n-form-item>
      <n-form-item label="URL">
        <n-input v-model:value="url" placeholder="https://..." />
      </n-form-item>
      <n-form-item :label="t('bookmarks.groupLabel')">
        <n-input v-model:value="group" :placeholder="t('bookmarks.groupPlaceholder')" />
      </n-form-item>
    </n-form>
    <template #action>
      <n-button @click="emit('update:show', false)">{{ t('common.cancel') }}</n-button>
      <n-button type="primary" :disabled="!title || !url" @click="submit">
        {{ t('common.save') }}
      </n-button>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NModal, NForm, NFormItem, NInput, NButton, useMessage } from 'naive-ui'
import { useLinksStore } from '../../stores/links'
import { isSafeHttpUrl } from '../../utils/url'

const props = defineProps<{
  show: boolean
}>()

const emit = defineEmits<{
  'update:show': [value: boolean]
}>()

const { t } = useI18n()
const store = useLinksStore()
const message = useMessage()

const title = ref('')
const url = ref('')
const group = ref('')

watch(() => props.show, (val) => {
  if (val) {
    title.value = ''
    url.value = ''
    group.value = ''
  }
})

async function submit() {
  if (!title.value || !url.value) return
  if (!isSafeHttpUrl(url.value)) {
    message.error(t('admin.links.form.invalidUrl'))
    return
  }
  await store.addBookmark({
    title: title.value,
    url: url.value,
    group_name: group.value || null,
  })
  emit('update:show', false)
}
</script>
