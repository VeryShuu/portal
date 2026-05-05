import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { VueQueryPlugin } from '@tanstack/vue-query'

import App from './App.vue'
import { router } from './router'
import { i18n, loadLocale, type AppLocale } from './i18n'

// Global styles (order matters: tokens → global → typography)
import './styles/tokens.css'
import './styles/global.css'
import './styles/typography.css'

const pinia = createPinia()

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
          retry: 1,
        },
      },
    },
  })

const savedLocale = (localStorage.getItem('lang') ?? 'ru') as AppLocale
if (savedLocale !== 'ru') {
  loadLocale(savedLocale).finally(() => app.mount('#app'))
} else {
  app.mount('#app')
}
