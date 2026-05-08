<template>
  <n-tooltip placement="bottom">
    <template #trigger>
      <n-button
        quaternary
        circle
        class="header-icon-btn"
        :aria-label="t('nav.toggleTheme')"
        @click="themeStore.toggle()"
      >
        <template #icon>
          <n-icon><SunnyOutline v-if="themeStore.isDark" /><MoonOutline v-else /></n-icon>
        </template>
      </n-button>
    </template>
    {{ t('nav.toggleTheme') }}
  </n-tooltip>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NButton, NIcon, NTooltip } from 'naive-ui'
import { SunnyOutline, MoonOutline } from '@vicons/ionicons5'
import { useThemeStore } from '../../stores/theme'

const { t } = useI18n()
const themeStore = useThemeStore()
</script>

<style scoped>
.header-icon-btn :deep(.n-icon) {
  color: rgba(255, 255, 255, 0.85);
}
.header-icon-btn:hover :deep(.n-icon) {
  color: #fff;
}
.header-icon-btn :deep(.n-button) {
  background: transparent;
}
</style>
