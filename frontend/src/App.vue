<template>
  <n-config-provider
    :theme="theme"
    :theme-overrides="themeOverrides"
    :locale="naiveLocale"
    :date-locale="naiveDateLocale"
  >
    <n-global-style />
    <n-message-provider>
      <n-dialog-provider>
        <n-notification-provider>
          <router-view />
        </n-notification-provider>
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
import { computed, watchEffect } from 'vue'
import { NConfigProvider, NGlobalStyle, NMessageProvider, NDialogProvider, NNotificationProvider, darkTheme, ruRU, dateRuRU, enUS, dateEnUS } from 'naive-ui'
import { useI18n } from 'vue-i18n'
import { useThemeStore } from './stores/theme'
import { lightThemeOverrides, darkThemeOverrides } from './styles/naive-theme'

const themeStore = useThemeStore()
const { locale } = useI18n()

const theme = computed(() => (themeStore.isDark ? darkTheme : null))
const themeOverrides = computed(() => (themeStore.isDark ? darkThemeOverrides : lightThemeOverrides))
const naiveLocale = computed(() => (locale.value === 'ru' ? ruRU : enUS))
const naiveDateLocale = computed(() => (locale.value === 'ru' ? dateRuRU : dateEnUS))

// Sync data-theme attribute for CSS-token theming
watchEffect(() => {
  document.documentElement.dataset.theme = themeStore.isDark ? 'dark' : 'light'
})
</script>
