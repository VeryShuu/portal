<template>
  <n-config-provider :theme="theme" :locale="naiveLocale" :date-locale="naiveDateLocale">
    <n-global-style />
    <router-view />
  </n-config-provider>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { NConfigProvider, NGlobalStyle, darkTheme, lightTheme, ruRU, dateRuRU, enUS, dateEnUS } from 'naive-ui'
import { useI18n } from 'vue-i18n'
import { useThemeStore } from './stores/theme'

const themeStore = useThemeStore()
const { locale } = useI18n()

const theme = computed(() => (themeStore.isDark ? darkTheme : lightTheme))
const naiveLocale = computed(() => (locale.value === 'ru' ? ruRU : enUS))
const naiveDateLocale = computed(() => (locale.value === 'ru' ? dateRuRU : dateEnUS))
</script>
