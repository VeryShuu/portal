<template>
  <n-layout-header bordered class="app-header">
    <div class="header-left">
      <n-button
        v-if="isMobile"
        quaternary
        circle
        class="header-icon-btn hamburger-btn"
        :aria-label="t('nav.openMenu')"
        :aria-expanded="drawerOpen"
        aria-controls="mobile-nav"
        @click="$emit('open-drawer')"
      >
        <template #icon><n-icon><MenuOutline /></n-icon></template>
      </n-button>
      <span class="header-title-default">{{ headerTitle }}</span>
    </div>

    <div class="header-center">
      <button class="search-pill" type="button" :aria-label="t('nav.openSearch')" @click="$emit('open-search')">
        <n-icon size="16"><SearchOutline /></n-icon>
        <span class="search-pill__label">{{ t('nav.searchHint') }}</span>
        <kbd class="search-pill__kbd">Ctrl K</kbd>
      </button>
    </div>

    <div class="header-right">
      <NotificationsDropdown />
      <HeaderThemeToggle />
      <HeaderLangSwitcher />
      <HeaderUserMenu :on-about="onAbout" />
    </div>
  </n-layout-header>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NButton, NIcon, NLayoutHeader } from 'naive-ui'
import { MenuOutline, SearchOutline } from '@vicons/ionicons5'
import NotificationsDropdown from '../NotificationsDropdown.vue'
import HeaderThemeToggle from './HeaderThemeToggle.vue'
import HeaderLangSwitcher from './HeaderLangSwitcher.vue'
import HeaderUserMenu from './HeaderUserMenu.vue'

defineProps<{
  isMobile: boolean
  drawerOpen: boolean
  headerTitle: string
  onAbout: () => void
}>()

defineEmits<{
  (e: 'open-drawer'): void
  (e: 'open-search'): void
}>()

const { t } = useI18n()
</script>

<style scoped>
.app-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 0 20px;
  height: var(--layout-header-height);
  background: rgba(11, 42, 74, 0.88);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  color: #fff;
  border-bottom: 1px solid var(--color-border) !important;
  position: sticky;
  top: 0;
  z-index: 100;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 200px;
}
.header-title-default {
  font-size: 17px;
  font-weight: 700;
  color: #fff;
  letter-spacing: -0.01em;
}
.header-center {
  flex: 1;
  display: flex;
  justify-content: center;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 4px;
}

.search-pill {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 36px;
  min-width: 280px;
  max-width: 480px;
  width: 100%;
  padding: 0 12px;
  background: rgba(255, 255, 255, 0.1);
  color: rgba(255, 255, 255, 0.85);
  border: 1px solid rgba(255, 255, 255, 0.16);
  border-radius: var(--radius-md);
  cursor: pointer;
  font-family: inherit;
  font-size: 13px;
  transition: background var(--t-fast), border-color var(--t-fast);
}
.search-pill:hover {
  background: rgba(255, 255, 255, 0.16);
  border-color: rgba(255, 255, 255, 0.28);
}
.search-pill__label {
  flex: 1;
  text-align: left;
  color: rgba(255, 255, 255, 0.7);
}
.search-pill__kbd {
  font-family: ui-monospace, monospace;
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.18);
  color: #fff;
  letter-spacing: 0.04em;
}

.header-icon-btn :deep(.n-icon) {
  color: rgba(255, 255, 255, 0.85);
}
.header-icon-btn:hover :deep(.n-icon) {
  color: #fff;
}
.header-icon-btn :deep(.n-button) {
  background: transparent;
}

@media (max-width: 900px) {
  .header-center { display: none; }
  .header-left { min-width: 0; }
  .search-pill { min-width: 0; }
}
@media (max-width: 767px) {
  .header-left { gap: 6px; }
}
</style>
