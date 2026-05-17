import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { VueQueryPlugin, QueryCache, MutationCache } from '@tanstack/vue-query'
import { createDiscreteApi } from 'naive-ui'

import App from './App.vue'
import { router } from './router'
import { i18n, loadLocale, type AppLocale } from './i18n'

// Global styles (order matters: tokens → global → typography → utilities → login)
import './styles/tokens.css'
import './styles/global.css'
import './styles/typography.css'
import './styles/utilities.css'
import './styles/login.css'
import 'flag-icons/css/flag-icons.min.css'

const pinia = createPinia()

const { message: globalMessage } = createDiscreteApi(['message'])

const app = createApp(App)

app
  .use(pinia)
  .use(router)
  .use(i18n)
  .use(VueQueryPlugin, {
    queryClientConfig: {
      defaultOptions: {
        queries: {
          staleTime: 30_000,
          gcTime: 5 * 60_000,
          retry: 1,
          refetchOnWindowFocus: false,
        },
        mutations: {
          retry: 0,
        },
      },
      queryCache: new QueryCache({
        onError: (err) => {
          console.error('[QueryCache]', err)
          const status = (err as { status?: number })?.status
          if (status && status >= 500) {
            globalMessage.error(i18n.global.t('errors.backendDown'))
          }
        },
      }),
      mutationCache: new MutationCache({
        onError: (err) => {
          console.error('[MutationCache]', err)
        },
      }),
    },
  })

const SUPPORTED_LOCALES: readonly AppLocale[] = ['ru', 'en']

function isAppLocale(value: string | null): value is AppLocale {
  return value !== null && (SUPPORTED_LOCALES as readonly string[]).includes(value)
}

const stored = localStorage.getItem('lang')
const savedLocale: AppLocale = isAppLocale(stored) ? stored : 'ru'
if (savedLocale !== 'ru') {
  loadLocale(savedLocale).finally(() => app.mount('#app'))
} else {
  app.mount('#app')
}
