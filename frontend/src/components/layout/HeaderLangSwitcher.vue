<template>
  <n-dropdown
    :options="langMenuOptions"
    placement="bottom-end"
    @select="handleLangSelect"
  >
    <n-button
      quaternary
      circle
      class="header-icon-btn header-icon-btn--lang"
      :aria-label="t('nav.switchLang')"
    >
      <span :class="['fi', locale === 'ru' ? 'fi-ru' : 'fi-gb', 'lang-flag']" />
    </n-button>
  </n-dropdown>
</template>

<script setup lang="ts">
import { computed, h } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NDropdown } from 'naive-ui'
import { loadLocale, type AppLocale } from '@/i18n'
import { patchMyProfile } from '../../api/users'

const { t, locale } = useI18n()

const langMenuOptions = computed(() => [
  {
    label: () => h('span', { class: 'lang-option' }, [
      h('span', { class: 'fi fi-ru lang-option__flag' }),
      h('span', {}, 'Русский'),
    ]),
    key: 'ru',
  },
  {
    label: () => h('span', { class: 'lang-option' }, [
      h('span', { class: 'fi fi-gb lang-option__flag' }),
      h('span', {}, 'English'),
    ]),
    key: 'en',
  },
])

async function handleLangSelect(key: string) {
  if (key === locale.value) return
  await loadLocale(key as AppLocale)
  locale.value = key
  localStorage.setItem('lang', key)
  try {
    await patchMyProfile({ lang: key as 'ru' | 'en' })
  } catch {
    // non-critical
  }
}
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
.header-icon-btn--lang {
  width: 36px;
}
.lang-flag {
  width: 20px;
  height: 15px;
  border-radius: 2px;
  display: inline-block;
  flex-shrink: 0;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.2);
}
:global(.lang-option) {
  display: flex;
  align-items: center;
  gap: 8px;
}
:global(.lang-option__flag) {
  width: 20px;
  height: 15px;
  border-radius: 2px;
  display: inline-block;
  flex-shrink: 0;
  box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.1);
}
</style>
