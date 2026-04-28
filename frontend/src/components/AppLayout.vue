<template>
  <a class="skip-link" href="#main-content">{{ t('a11y.skipToContent') }}</a>
  <n-layout has-sider class="app-shell">
    <n-layout-sider
      bordered
      collapse-mode="width"
      :collapsed-width="64"
      :width="240"
      :collapsed="collapsed"
      show-trigger="bar"
      class="app-sider"
      @collapse="collapsed = true"
      @expand="collapsed = false"
    >
      <div class="logo-wrap" @click="router.push('/')">
        <img v-if="logoUrl" :src="logoUrl" class="logo-img" alt="Logo" />
        <div v-else class="logo-mark">
          <span class="logo-mark__dot" />
        </div>
      </div>

      <n-menu
        :collapsed="collapsed"
        :collapsed-width="64"
        :collapsed-icon-size="22"
        :options="menuOptions"
        :value="activeKey"
        :indent="18"
        @update:value="handleMenuSelect"
      />

      <div class="sider-footer"></div>
    </n-layout-sider>

    <n-layout class="app-main">
      <n-layout-header bordered class="app-header">
        <div class="header-left">
          <span class="header-title-default">{{ layoutHeader.headerText.value || defaultTitle }}</span>
        </div>

        <div class="header-center">
          <button class="search-pill" type="button" :aria-label="t('nav.openSearch')" @click="openSearch">
            <n-icon size="16"><SearchOutline /></n-icon>
            <span class="search-pill__label">{{ t('nav.searchHint') }}</span>
            <kbd class="search-pill__kbd">Ctrl K</kbd>
          </button>
        </div>

        <div class="header-right">
          <NotificationsDropdown />

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

          <n-tooltip placement="bottom">
            <template #trigger>
              <n-button
                quaternary
                circle
                class="header-icon-btn header-icon-btn--lang"
                :aria-label="t('nav.switchLang')"
                @click="toggleLang"
              >
                <span class="lang-text">{{ locale.toUpperCase() }}</span>
              </n-button>
            </template>
            {{ t('nav.switchLang') }}
          </n-tooltip>

          <n-dropdown :options="userMenuOptions" placement="bottom-end" @select="handleUserAction">
            <button class="user-pill" type="button">
              <n-avatar
                round
                :size="30"
                :src="auth.user?.avatar_url ?? undefined"
                color="#d8262c"
              >
                <template v-if="!auth.user?.avatar_url">{{ initials }}</template>
              </n-avatar>
              <span class="user-pill__name">{{ auth.user?.full_name }}</span>
              <n-icon size="14" class="user-pill__chev"><ChevronDownOutline /></n-icon>
            </button>
          </n-dropdown>
        </div>
      </n-layout-header>

      <n-layout-content id="main-content" tag="main" class="app-content" :aria-label="t('a11y.mainContent')">
        <RouterView />
      </n-layout-content>
    </n-layout>

    <GlobalSearch v-model:show="searchOpen" />
  </n-layout>
</template>

<script setup lang="ts">
import { computed, h, ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { RouterView, useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  NLayout, NLayoutSider, NLayoutHeader, NLayoutContent,
  NMenu, NButton, NIcon, NDropdown, NAvatar, NTooltip,
  type MenuOption,
} from 'naive-ui'
import {
  HomeOutline, NewspaperOutline, BookOutline, FolderOpenOutline,
  GridOutline, BookmarkOutline, PersonOutline, SettingsOutline,
  SunnyOutline, MoonOutline, SearchOutline,
  ChevronDownOutline, ImagesOutline, VideocamOutline,
} from '@vicons/ionicons5'
import { useAuthStore } from '../stores/auth'
import { useThemeStore } from '../stores/theme'
import { useNotificationsStore } from '../stores/notifications'
import { useBrandingStore } from '../stores/branding'
import { patchMyProfile } from '../api/users'
import { api } from '../api/index'
import GlobalSearch from './GlobalSearch.vue'
import NotificationsDropdown from './NotificationsDropdown.vue'
import { useLayoutHeader } from '../composables/useLayoutHeader'

const router = useRouter()
const route = useRoute()
const { t, locale } = useI18n()
const auth = useAuthStore()
const themeStore = useThemeStore()
const notificationsStore = useNotificationsStore()
const brandingStore = useBrandingStore()
const layoutHeader = useLayoutHeader()

const collapsed = ref(localStorage.getItem('sider-collapsed') === '1')
const searchOpen = ref(false)
const logoUrl = ref<string | null>(null)
const photoGalleryUrl = ref<string | null>(null)
const videoGalleryUrl = ref<string | null>(null)

watch(
  () => brandingStore.settings.has_logo,
  (hasLogo) => { logoUrl.value = hasLogo ? `/api/v1/branding/logo?t=${Date.now()}` : null },
  { immediate: true },
)

async function refreshLogo() {
  await brandingStore.load()
  logoUrl.value = brandingStore.settings.has_logo ? `/api/v1/branding/logo?t=${Date.now()}` : null
}

function isInternalUrl(url: string | null): boolean {
  return !!url && url.startsWith('/') && !url.startsWith('//')
}

const activeKey = computed(() => {
  const path = route.path
  if (path.startsWith('/news')) return 'news'
  if (path.startsWith('/kb')) return 'kb'
  if (path.startsWith('/files')) return 'files'
  if (path.startsWith('/links')) return 'links'
  if (path.startsWith('/bookmarks')) return 'bookmarks'
  if (path.startsWith('/photos')) return 'photo-gallery'
  if (path.startsWith('/profile')) return 'profile'
  if (path.startsWith('/admin')) return 'admin'
  return 'home'
})

const defaultTitle = computed(() => {
  const map: Record<string, string> = {
    home: t('nav.home'),
    news: t('nav.news'),
    kb: t('nav.kb'),
    files: t('nav.files'),
    links: t('nav.links'),
    bookmarks: t('nav.bookmarks'),
    'photo-gallery': t('nav.photoGallery'),
    profile: t('nav.profile'),
    admin: t('nav.admin'),
  }
  return map[activeKey.value] ?? ''
})

const initials = computed(() => {
  const name = auth.user?.full_name ?? ''
  return name.split(' ').slice(0, 2).map(w => w[0]).join('').toUpperCase()
})

const roleLabel = computed(() => {
  if (!auth.user) return ''
  if (auth.user.role === 'admin') return t('admin.users.role.admin')
  if (auth.user.role === 'editor') return t('admin.users.role.editor')
  return t('admin.users.role.reader')
})

function renderIcon(icon: any) {
  return () => h(NIcon, null, { default: () => h(icon) })
}

function groupLabel(label: string) {
  return () => h('span', { class: 'menu-group-label' }, label)
}

const menuOptions = computed<MenuOption[]>(() => {
  const items: MenuOption[] = [
    {
      type: 'group',
      key: 'g-feed',
      label: groupLabel(t('nav.groups.feed')),
      children: [
        { label: t('nav.home'), key: 'home', icon: renderIcon(HomeOutline) },
        { label: t('nav.news'), key: 'news', icon: renderIcon(NewspaperOutline) },
      ],
    },
    {
      type: 'group',
      key: 'g-work',
      label: groupLabel(t('nav.groups.work')),
      children: [
        { label: t('nav.kb'), key: 'kb', icon: renderIcon(BookOutline) },
        { label: t('nav.files'), key: 'files', icon: renderIcon(FolderOpenOutline) },
      ],
    },
    {
      type: 'group',
      key: 'g-services',
      label: groupLabel(t('nav.groups.services')),
      children: [
        { label: t('nav.links'), key: 'links', icon: renderIcon(GridOutline) },
        { label: t('nav.bookmarks'), key: 'bookmarks', icon: renderIcon(BookmarkOutline) },
        ...(photoGalleryUrl.value
          ? [{ label: t('nav.photoGallery'), key: 'photo-gallery', icon: renderIcon(ImagesOutline) }]
          : []),
        ...(videoGalleryUrl.value
          ? [{ label: t('nav.videoGallery'), key: 'video-gallery', icon: renderIcon(VideocamOutline) }]
          : []),
      ],
    },
    {
      type: 'group',
      key: 'g-account',
      label: groupLabel(t('nav.groups.account')),
      children: [
        { label: t('nav.profile'), key: 'profile', icon: renderIcon(PersonOutline) },
        ...(auth.isAdmin
          ? [{ label: t('nav.admin'), key: 'admin', icon: renderIcon(SettingsOutline) }]
          : []),
      ],
    },
  ]
  return items
})

const routeMap: Record<string, string> = {
  home: '/',
  news: '/news',
  kb: '/kb',
  files: '/files',
  links: '/links',
  bookmarks: '/bookmarks',
  profile: '/profile',
  admin: '/admin',
}

function handleMenuSelect(key: string) {
  if (key === 'photo-gallery' && photoGalleryUrl.value) {
    if (isInternalUrl(photoGalleryUrl.value)) {
      router.push(photoGalleryUrl.value)
    } else {
      window.open(photoGalleryUrl.value, '_blank', 'noopener,noreferrer')
    }
    return
  }
  if (key === 'video-gallery' && videoGalleryUrl.value) {
    if (isInternalUrl(videoGalleryUrl.value)) {
      router.push(videoGalleryUrl.value)
    } else {
      window.open(videoGalleryUrl.value, '_blank', 'noopener,noreferrer')
    }
    return
  }
  router.push(routeMap[key] ?? '/')
}

async function loadGalleryLinks() {
  try {
    const data = await api<{ photo_gallery_url: string | null; video_gallery_url: string | null }>('/portal/gallery-links')
    photoGalleryUrl.value = data.photo_gallery_url ?? null
    videoGalleryUrl.value = data.video_gallery_url ?? null
  } catch {
    // non-critical
  }
}

const userMenuOptions = computed(() => [
  { label: t('nav.profile'), key: 'profile' },
  { type: 'divider', key: 'd1' },
  { label: t('auth.logout'), key: 'logout' },
])

function handleUserAction(key: string) {
  if (key === 'logout') auth.logout()
  if (key === 'profile') router.push('/profile')
}

async function toggleLang() {
  const newLang = locale.value === 'ru' ? 'en' : 'ru'
  locale.value = newLang
  localStorage.setItem('lang', newLang)
  try {
    await patchMyProfile({ lang: newLang as 'ru' | 'en' })
  } catch {
    // non-critical
  }
}

function openSearch() {
  searchOpen.value = true
}

// Keyboard: Ctrl/Cmd+K opens search (+ custom event from HeroBlock)
function onKeydown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault()
    openSearch()
  }
}
function onOpenEvent() {
  openSearch()
}
// P1-25: register/unregister listeners on lifecycle to avoid leaks across
// HMR reloads and route teardown.
onMounted(() => {
  if (typeof window === 'undefined') return
  window.addEventListener('keydown', onKeydown)
  window.addEventListener('open-global-search', onOpenEvent)
  window.addEventListener('logo-updated', refreshLogo as EventListener)
  notificationsStore.init()
  loadGalleryLinks()
})

onBeforeUnmount(() => {
  if (typeof window === 'undefined') return
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('open-global-search', onOpenEvent)
  window.removeEventListener('logo-updated', refreshLogo as EventListener)
  notificationsStore.disconnectSSE()
})

// Persist collapsed state
watch(collapsed, (v) => {
  localStorage.setItem('sider-collapsed', v ? '1' : '0')
})
</script>

<style scoped>
.app-shell {
  min-height: 100vh;
  background: var(--color-bg);
}

/* === Sider === */
.app-sider {
  background: var(--color-surface);
  display: flex;
  flex-direction: column;
}
.app-sider :deep(.n-layout-sider-scroll-container) {
  display: flex;
  flex-direction: column;
}
.logo-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 14px 18px;
  cursor: pointer;
  user-select: none;
  min-height: var(--layout-header-height);
  border-bottom: 1px solid var(--color-border);
}
.logo-img {
  max-height: 40px;
  max-width: 180px;
  object-fit: contain;
}
.logo-mark {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
  background: var(--gradient-hero);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  position: relative;
  box-shadow: var(--shadow-sm);
}
.logo-mark__dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--color-brand-red);
  box-shadow: 0 0 0 3px rgba(216, 38, 44, 0.18);
}
.logo-text__title {
  font-size: 14px;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--color-text);
  line-height: 1.2;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 160px;
}
.logo-text__subtitle {
  font-size: 11px;
  color: var(--color-text-subtle);
  letter-spacing: 0.05em;
  text-transform: uppercase;
  margin-top: 2px;
}

:deep(.menu-group-label) {
  text-transform: uppercase;
  letter-spacing: 0.1em;
  font-size: 10px;
  font-weight: 700;
  color: var(--color-text-subtle);
}

/* Hover state on menu items */
.app-sider :deep(.n-menu-item-content:not(.n-menu-item-content--selected):hover) {
  background: var(--color-bg-muted) !important;
}

/* Active item indicator: red left bar */
.app-sider :deep(.n-menu-item-content--selected)::before {
  content: '';
  position: absolute;
  left: 0;
  top: 6px;
  bottom: 6px;
  width: 3px;
  border-radius: 0 3px 3px 0;
  background: var(--color-brand-red);
}
.app-sider :deep(.n-menu-item-content) {
  position: relative;
}

.sider-footer {
  margin-top: auto;
  border-top: 1px solid var(--color-border);
  padding: 12px;
}
.sider-user {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 6px;
}
.sider-user__meta {
  min-width: 0;
}
.sider-user__name {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 160px;
}
.sider-user__pos {
  font-size: 11px;
  color: var(--color-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 160px;
}

/* === Header === */
.app-main {
  background: var(--color-bg);
}
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
  border-bottom: none !important;
  box-shadow: var(--shadow-sm);
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

/* Header buttons — white over navy */
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
.lang-text {
  font-size: 12px;
  font-weight: 700;
  color: rgba(255, 255, 255, 0.85);
  letter-spacing: 0.05em;
}

.user-pill {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 10px 4px 4px;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: var(--radius-pill);
  cursor: pointer;
  font-family: inherit;
  color: #fff;
  margin-left: 8px;
  transition: background var(--t-fast);
}
.user-pill:hover {
  background: rgba(255, 255, 255, 0.16);
}
.user-pill__name {
  font-size: 13px;
  font-weight: 600;
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.user-pill__chev {
  opacity: 0.7;
}

/* === Content === */
.app-content {
  padding: 24px 28px;
  min-height: calc(100vh - var(--layout-header-height));
  background: var(--color-bg);
  overflow-y: auto;
  scrollbar-gutter: stable;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.18s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* === Responsive === */
@media (max-width: 900px) {
  .header-center { display: none; }
  .header-left { min-width: 0; }
  .user-pill__name { display: none; }
  .search-pill { min-width: 0; }
}
@media (max-width: 600px) {
  .app-content { padding: 16px; }
  .lang-text { font-size: 11px; }
}
</style>
