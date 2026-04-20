import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from './stores/auth'

export const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/auth/callback',
      name: 'auth-callback',
      component: () => import('./pages/AuthCallbackPage.vue'),
    },
    {
      path: '/',
      name: 'home',
      component: () => import('./pages/HomePage.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/news',
      name: 'news-list',
      component: () => import('./pages/NewsListPage.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/news/create',
      name: 'news-create',
      component: () => import('./pages/NewsFormPage.vue'),
      meta: { requiresAuth: true, requiresEditor: true },
    },
    {
      path: '/news/:id',
      name: 'news-detail',
      component: () => import('./pages/NewsDetailPage.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/news/:id/edit',
      name: 'news-edit',
      component: () => import('./pages/NewsFormPage.vue'),
      meta: { requiresAuth: true, requiresEditor: true },
    },
    {
      path: '/profile',
      name: 'profile',
      component: () => import('./pages/ProfilePage.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/kb',
      name: 'kb',
      component: () => import('./pages/KbPlaceholderPage.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/links',
      name: 'links',
      component: () => import('./pages/LinksPlaceholderPage.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: () => import('./pages/NotFoundPage.vue'),
    },
  ],
})

router.beforeEach(async (to) => {
  if (!to.meta.requiresAuth) return true

  const auth = useAuthStore()
  if (!auth.isAuthenticated) {
    const ok = await auth.loadUser()
    if (!ok) {
      auth.redirectToLogin(to.fullPath)
      return false
    }
  }

  if (to.meta.requiresEditor && !auth.isEditor) {
    return { name: 'home' }
  }

  return true
})
