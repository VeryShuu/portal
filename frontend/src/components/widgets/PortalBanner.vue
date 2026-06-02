<template>
  <div
    v-if="showBanner"
    class="portal-banner"
    :class="`portal-banner--${branding.settings.banner_type}`"
    role="alert"
  >
    <span class="portal-banner__text">{{ branding.settings.banner_text }}</span>
    <button
      class="portal-banner__close"
      :aria-label="t('common.close')"
      @click="dismissBanner"
    >
      ✕
    </button>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useHomeBannerDismiss } from '../../pages/composables/useHomeBannerDismiss'

const { t } = useI18n()
const { branding, showBanner, dismissBanner } = useHomeBannerDismiss()
</script>

<style scoped>
.portal-banner {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 18px;
  border-radius: var(--radius-md);
  margin-bottom: 16px;
  font-size: 14px;
  font-weight: 500;
}
.portal-banner--info    { background: #e0eafc; color: #1a4b8c; }
.portal-banner--warning { background: #fef3c7; color: #92400e; }
.portal-banner--error   { background: #fde8e9; color: #9b1c1c; }
.portal-banner--success { background: #dcfce7; color: #14532d; }
.portal-banner__text { flex: 1; }
.portal-banner__close {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 16px;
  opacity: 0.6;
  padding: 0 4px;
  color: inherit;
  line-height: 1;
}
.portal-banner__close:hover { opacity: 1; }
</style>
