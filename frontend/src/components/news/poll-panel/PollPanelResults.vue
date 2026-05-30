<template>
  <div class="poll-empty-state">
    <n-button
      type="primary"
      dashed
      @click="$emit('create')"
    >
      <template #icon>
        <n-icon><AddOutline /></n-icon>
      </template>
      {{ t('news.poll.editor.addPoll') }}
    </n-button>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NButton, NIcon } from 'naive-ui'
import { AddOutline } from '@vicons/ionicons5'

defineEmits<{
  create: []
}>()

const { t } = useI18n()
</script>

<style scoped>
.poll-empty-state {
  display: flex;
  justify-content: center;
  padding: 16px 0;
}
</style>
