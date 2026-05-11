<template>
  <a class="skip-link" href="#main-content">{{ t('a11y.skipToContent') }}</a>

  <AppMobileDrawer
    v-model:show="drawerOpen"
    :logo-url="logoUrl"
    :menu-options="menuOptions"
    :active-key="activeKey"
    @select="handleMenuSelect"
  />

  <n-layout has-sider class="app-shell">
    <AppSider
      v-if="!isMobile"
      v-model:collapsed="collapsed"
      :logo-url="logoUrl"
      :menu-options="menuOptions"
      :active-key="activeKey"
      @select="handleMenuSelect"
    />

    <n-layout class="app-main">
      <AppHeader
        :is-mobile="isMobile"
        :drawer-open="drawerOpen"
        :header-title="layoutHeader.headerText || defaultTitle"
        :on-about="startTour"
        @open-drawer="drawerOpen = true"
        @open-search="openSearch"
      />

      <div v-if="auth.backendDown" class="backend-down-banner" role="alert">
        {{ t('errors.backendDown') }}
      </div>

      <n-layout-content id="main-content" tag="main" class="app-content" :aria-label="t('a11y.mainContent')">
        <RouterView />
      </n-layout-content>
    </n-layout>

    <GlobalSearch v-model:show="searchOpen" />
    <OnboardingTour ref="tourRef" />
    <FeedbackModal />
  </n-layout>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { NLayout, NLayoutContent } from 'naive-ui'
import { useAuthStore } from '../stores/auth'
import { useNotificationsStore } from '../stores/notifications'
import { useBrandingStore } from '../stores/branding'
import GlobalSearch from './GlobalSearch.vue'
import OnboardingTour from './OnboardingTour.vue'
import FeedbackModal from './FeedbackModal.vue'
import AppSider from './layout/AppSider.vue'
import AppMobileDrawer from './layout/AppMobileDrawer.vue'
import AppHeader from './layout/AppHeader.vue'
import { useLayoutHeader } from '../composables/useLayoutHeader'
import { useBreakpoints } from '../composables/useBreakpoints'
import { useGlobalHotkeys } from '../composables/useGlobalHotkeys'
import { useAppMenu } from '../composables/useAppMenu'

const route = useRoute()
const { t } = useI18n()
const auth = useAuthStore()
const notificationsStore = useNotificationsStore()
const brandingStore = useBrandingStore()
const layoutHeader = useLayoutHeader()

const { isMobile, isTablet } = useBreakpoints()
const { menuOptions, activeKey, defaultTitle, handleMenuSelect } = useAppMenu()

const collapsed = ref(localStorage.getItem('sider-collapsed') === '1')
const searchOpen = ref(false)
const tourRef = ref<{ startTour: () => void } | null>(null)
const logoUrl = ref<string | null>(null)
const drawerOpen = ref(false)

function openSearch() {
  searchOpen.value = true
}

function startTour() {
  tourRef.value?.startTour()
}

useGlobalHotkeys({ onOpenSearch: openSearch })

watch(
  () => [brandingStore.settings.has_logo, brandingStore.settings.logo_updated_at] as const,
  ([hasLogo, updatedAt]) => {
    logoUrl.value = hasLogo ? `/api/v1/branding/logo?v=${encodeURIComponent(updatedAt ?? '1')}` : null
  },
  { immediate: true },
)

async function refreshLogo() {
  await brandingStore.load()
  const { has_logo, logo_updated_at } = brandingStore.settings
  logoUrl.value = has_logo ? `/api/v1/branding/logo?v=${encodeURIComponent(logo_updated_at ?? '1')}` : null
}

onMounted(() => {
  if (typeof window === 'undefined') return
  if (isTablet.value && !localStorage.getItem('sider-collapsed')) collapsed.value = true
  window.addEventListener('logo-updated', refreshLogo as EventListener)
  notificationsStore.initSSEOnly()
})

onBeforeUnmount(() => {
  if (typeof window === 'undefined') return
  window.removeEventListener('logo-updated', refreshLogo as EventListener)
  notificationsStore.disconnectSSE()
})

watch(collapsed, (v) => {
  localStorage.setItem('sider-collapsed', v ? '1' : '0')
})

watch(isTablet, (val) => {
  if (val) collapsed.value = true
})

watch(() => route.path, () => {
  if (drawerOpen.value) drawerOpen.value = false
})
</script>

<style scoped>
.app-shell {
  min-height: 100vh;
  background: var(--color-bg);
}
.app-main {
  background: var(--color-bg);
}

.backend-down-banner {
  background: var(--error-color, #e03131);
  color: #fff;
  text-align: center;
  padding: 8px 16px;
  font-size: 14px;
  font-weight: 500;
}

.app-content {
  padding: 24px 28px;
  min-height: calc(100vh - var(--layout-header-height));
  background: var(--color-bg);
  overflow-y: auto;
  scrollbar-gutter: stable;
}

@media (max-width: 767px) {
  .app-content { padding: 16px; }
}
</style>
