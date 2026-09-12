<template>
  <div class="branding-wrap">
    <div class="branding-section">
      <div class="branding-section__title">
        {{ t('admin.matrix.title') }}
      </div>
      <div class="branding-section__hint">
        {{ t('admin.matrix.sectionHint') }}
      </div>
      <MatrixBotSettings />
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import MatrixBotSettings from '../../../components/admin/MatrixBotSettings.vue'

const { t } = useI18n()
</script>

<style scoped>
@import '../admin-tabs.css';
</style>
