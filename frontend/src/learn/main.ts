/**
 * Точка входа learn-контура (ADR-051, ТЗ §9): отдельная сборка без портальных
 * страниц. Общая кодовая база (i18n, design-tokens, api-клиент, learner-страницы
 * портала) — но свой router и layout; SSO/Keycloak здесь нет по построению.
 */
import { createApp } from 'vue'
import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query'

import LearnApp from './LearnApp.vue'
import { createLearnRouter } from './router'
import { i18n } from '../i18n'
import { listenAuthExpired } from './authGuard'

// Global styles: те же токены дизайна (единый визуальный язык портала);
// login.css не нужен — у learn-страниц свои scoped-стили.
import '../styles/tokens.css'
import '../styles/global.css'
import '../styles/typography.css'
import '../styles/utilities.css'
import './learning-theme.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, gcTime: 5 * 60_000, retry: 1, refetchOnWindowFocus: false },
    mutations: { retry: 0 },
  },
})

const app = createApp(LearnApp)

const router = createLearnRouter()
listenAuthExpired(router)

app.use(router).use(i18n).use(VueQueryPlugin, { queryClient })

app.mount('#learn-app')
