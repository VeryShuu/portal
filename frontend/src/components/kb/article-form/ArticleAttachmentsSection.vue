<template>
  <KbAttachmentsPanel
    v-if="isEdit && articleId"
    :article-id="articleId"
    :can-upload="true"
  />
</template>

<script setup lang="ts">
import KbAttachmentsPanel from '../../KbAttachmentsPanel.vue'

defineProps<{
  articleId: string | undefined
  isEdit: boolean
}>()
</script>
