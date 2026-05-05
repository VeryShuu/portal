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
import { computed, watchEffect, onMounted } from 'vue'
import { NConfigProvider, NGlobalStyle, NMessageProvider, NDialogProvider, NNotificationProvider, darkTheme, ruRU, dateRuRU, enUS, dateEnUS } from 'naive-ui'
import { useI18n } from 'vue-i18n'
import { useThemeStore } from './stores/theme'
import { useBrandingStore } from './stores/branding'
import { useModulesStore } from './stores/modules'
import { useAuthStore } from './stores/auth'

const themeStore = useThemeStore()
const brandingStore = useBrandingStore()
const modulesStore = useModulesStore()
const authStore = useAuthStore()
const { locale } = useI18n()

const theme = computed(() => (themeStore.isDark ? darkTheme : null))
const themeOverrides = computed(() => (themeStore.isDark ? brandingStore.darkOverrides : brandingStore.lightOverrides))
const naiveLocale = computed(() => (locale.value === 'ru' ? ruRU : enUS))
const naiveDateLocale = computed(() => (locale.value === 'ru' ? dateRuRU : dateEnUS))

watchEffect(() => {
  document.documentElement.dataset.theme = themeStore.isDark ? 'dark' : 'light'
})

onMounted(() => {
  brandingStore.load()
  if (authStore.isAuthenticated) {
    modulesStore.load().catch(() => {})
  }
})
</script>
