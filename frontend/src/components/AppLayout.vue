<template>
  <n-layout has-sider style="min-height: 100vh">
    <n-layout-sider
      bordered
      collapse-mode="width"
      :collapsed-width="64"
      :width="220"
      :collapsed="collapsed"
      show-trigger
      @collapse="collapsed = true"
      @expand="collapsed = false"
    >
      <div class="logo-wrap" @click="router.push('/')">
        <n-icon size="28" color="#18a058"><HomeOutline /></n-icon>
        <transition name="fade">
          <span v-if="!collapsed" class="logo-text">{{ t('app.title') }}</span>
        </transition>
      </div>

      <n-menu
        :collapsed="collapsed"
        :collapsed-width="64"
        :collapsed-icon-size="22"
        :options="menuOptions"
        :value="activeKey"
        @update:value="handleMenuSelect"
      />
    </n-layout-sider>

    <n-layout>
      <n-layout-header bordered class="header">
        <div class="header-left">
          <slot name="header-title" />
        </div>
        <div class="header-right">
          <n-button quaternary @click="themeStore.toggle()">
            <template #icon>
              <n-icon><SunnyOutline v-if="themeStore.isDark" /><MoonOutline v-else /></n-icon>
            </template>
          </n-button>

          <n-button quaternary @click="toggleLang">
            <span style="font-size:13px;font-weight:600">{{ locale.toUpperCase() }}</span>
          </n-button>

          <n-dropdown :options="userMenuOptions" @select="handleUserAction">
            <n-button quaternary class="user-btn">
              <n-avatar
                round
                :size="32"
                :src="auth.user?.avatar_url ?? undefined"
                :fallback-src="undefined"
              >
                <template v-if="!auth.user?.avatar_url">
                  {{ initials }}
                </template>
              </n-avatar>
              <transition name="fade">
                <span v-if="!isNarrow" class="user-name">{{ auth.user?.full_name }}</span>
              </transition>
            </n-button>
          </n-dropdown>
        </div>
      </n-layout-header>

      <n-layout-content class="content">
        <slot />
      </n-layout-content>
    </n-layout>
  </n-layout>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  NLayout, NLayoutSider, NLayoutHeader, NLayoutContent,
  NMenu, NButton, NIcon, NDropdown, NAvatar,
  type MenuOption,
} from 'naive-ui'
import {
  HomeOutline, NewspaperOutline, BookOutline,
  GridOutline, PersonOutline, SettingsOutline,
  SunnyOutline, MoonOutline,
} from '@vicons/ionicons5'
import { h } from 'vue'
import { useAuthStore } from '../stores/auth'
import { useThemeStore } from '../stores/theme'
import { patchMyProfile } from '../api/users'

const router = useRouter()
const route = useRoute()
const { t, locale } = useI18n()
const auth = useAuthStore()
const themeStore = useThemeStore()

const collapsed = ref(false)
const isNarrow = computed(() => collapsed.value)

const activeKey = computed(() => {
  const path = route.path
  if (path.startsWith('/news')) return 'news'
  if (path.startsWith('/kb')) return 'kb'
  if (path.startsWith('/links')) return 'links'
  if (path.startsWith('/profile')) return 'profile'
  if (path.startsWith('/admin')) return 'admin'
  return 'home'
})

const initials = computed(() => {
  const name = auth.user?.full_name ?? ''
  return name.split(' ').slice(0, 2).map(w => w[0]).join('').toUpperCase()
})

function renderIcon(icon: any) {
  return () => h(NIcon, null, { default: () => h(icon) })
}

const menuOptions = computed<MenuOption[]>(() => {
  const items: MenuOption[] = [
    { label: t('nav.home'), key: 'home', icon: renderIcon(HomeOutline) },
    { label: t('nav.news'), key: 'news', icon: renderIcon(NewspaperOutline) },
    { label: t('nav.kb'), key: 'kb', icon: renderIcon(BookOutline) },
    { label: t('nav.links'), key: 'links', icon: renderIcon(GridOutline) },
    { label: t('nav.profile'), key: 'profile', icon: renderIcon(PersonOutline) },
  ]
  if (auth.isAdmin) {
    items.push({ label: t('nav.admin'), key: 'admin', icon: renderIcon(SettingsOutline) })
  }
  return items
})

const routeMap: Record<string, string> = {
  home: '/',
  news: '/news',
  kb: '/kb',
  links: '/links',
  profile: '/profile',
  admin: '/admin',
}

function handleMenuSelect(key: string) {
  router.push(routeMap[key] ?? '/')
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
</script>

<style scoped>
.logo-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px 20px;
  cursor: pointer;
  user-select: none;
  min-height: 60px;
}
.logo-text {
  font-size: 15px;
  font-weight: 700;
  white-space: nowrap;
  overflow: hidden;
}
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  height: 60px;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 4px;
}
.user-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
}
.user-name {
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
}
.content {
  padding: 24px;
  min-height: calc(100vh - 60px);
}
.fade-enter-active, .fade-leave-active { transition: opacity .2s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
