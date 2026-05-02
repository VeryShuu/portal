import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { VueQueryPlugin } from '@tanstack/vue-query'
import { createI18n } from 'vue-i18n'

import App from './App.vue'
import { router } from './router'
import ru from './i18n/ru.json'
import en from './i18n/en.json'

// Global styles (order matters: tokens → global → typography)
import './styles/tokens.css'
import './styles/global.css'
import './styles/typography.css'

const i18n = createI18n({
  legacy: false,
  locale: localStorage.getItem('lang') ?? 'ru',
  fallbackLocale: 'ru',
  messages: { ru, en },
})

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
  .mount('#app')
