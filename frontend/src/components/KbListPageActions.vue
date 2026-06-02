<template>
  <div class="page-head__right u-page-head__actions">
    <n-button
      v-if="isAdmin"
      size="medium"
      quaternary
      circle
      :title="t('admin.tabs.kb')"
      @click="emit('manage')"
    >
      <template #icon>
        <n-icon :component="SettingsOutline" />
      </template>
    </n-button>
    <n-button
      v-if="isAdmin"
      size="medium"
      quaternary
      :title="t('kb.trash.openTitle')"
      @click="emit('open-trash')"
    >
      <template #icon>
        <n-icon :component="TrashOutline" />
      </template>
      {{ t('kb.trash.short') }}
    </n-button>
    <n-button
      v-if="selectedSection"
      size="medium"
      @click="emit('export-section')"
    >
      ⬇ {{ t('kb.export.sectionZip') }}
    </n-button>
    <n-button
      v-if="isEditor"
      size="medium"
      @click="emit('open-import')"
    >
      ⬆ {{ t('kb.import.title') }}
    </n-button>
    <n-button
      v-if="canCreateArticle"
      type="primary"
      size="medium"
      @click="emit('create-article')"
    >
      + {{ t('kb.createArticle') }}
    </n-button>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NButton, NIcon } from 'naive-ui'
import { SettingsOutline, TrashOutline } from '@vicons/ionicons5'

defineProps<{
  isAdmin: boolean
  isEditor: boolean
  canCreateArticle: boolean
  selectedSection: string | null
}>()

const emit = defineEmits<{
  (e: 'manage'): void
  (e: 'open-trash'): void
  (e: 'export-section'): void
  (e: 'open-import'): void
  (e: 'create-article'): void
}>()

const { t } = useI18n()
</script>
