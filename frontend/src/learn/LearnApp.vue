<template>
  <n-config-provider :theme-overrides="learnThemeOverrides">
    <n-global-style />
    <n-message-provider>
      <n-dialog-provider>
        <n-notification-provider>
          <div class="learn-shell">
            <a
              class="skip-link"
              href="#learn-main"
            >
              {{ t('learning.learn.skipToContent') }}
            </a>
            <header class="learn-shell__head">
              <RouterLink
                class="learn-shell__brand"
                to="/courses"
              >
                <span
                  class="learn-shell__brand-mark"
                  aria-hidden="true"
                >
                  <n-icon :size="22">
                    <SchoolOutline />
                  </n-icon>
                </span>
                <span class="learn-shell__brand-copy">
                  <span class="learn-shell__brand-eyebrow">
                    {{ t('learning.learn.brandEyebrow') }}
                  </span>
                  <span class="learn-shell__brand-name">
                    {{ t('learning.learn.brand') }}
                  </span>
                </span>
              </RouterLink>
              <n-button
                v-if="route.name !== 'learn-login' && authed"
                quaternary
                size="small"
                @click="onLogout"
              >
                {{ t('learning.learn.logout') }}
              </n-button>
            </header>

            <main
              id="learn-main"
              class="learn-shell__main"
              tabindex="-1"
            >
              <RouterView />
            </main>
          </div>
        </n-notification-provider>
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter, RouterLink, RouterView } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  NButton,
  NConfigProvider,
  NDialogProvider,
  NGlobalStyle,
  NIcon,
  NMessageProvider,
  NNotificationProvider,
} from 'naive-ui'
import { SchoolOutline } from '@vicons/ionicons5'
import type { GlobalThemeOverrides } from 'naive-ui'
import { learnerLogout } from '../api/learningAuth'
import { lightThemeOverrides } from '../styles/naive-theme'

// Public learner pages use the Portal palette with AA contrast for small
// status text, input hints and secondary buttons on their light surfaces.
const learnThemeOverrides: GlobalThemeOverrides = {
  ...lightThemeOverrides,
  common: {
    ...lightThemeOverrides.common,
    placeholderColor: '#64748b',
    infoColor: '#1f4e85',
    infoColorHover: '#143a66',
    infoColorPressed: '#0b2a4a',
    infoColorSuppl: '#143a66',
    successColor: '#15803d',
  },
  Tag: {
    ...lightThemeOverrides.Tag,
    textColorSuccess: '#166534',
  },
  Empty: {
    ...lightThemeOverrides.Empty,
    textColor: '#475569',
  },
}

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

// Кнопка «Выйти» — только на страницах за сессией (курсы/тест).
const authed = computed(() => route.name !== 'learn-login')

async function onLogout() {
  try {
    await learnerLogout()
  } catch {
    // cookie может уже не быть — локальный выход всё равно выполняем
  }
  await router.push({ name: 'learn-login' })
}
</script>
