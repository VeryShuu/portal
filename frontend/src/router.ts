import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from './stores/auth'

export const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('./pages/LoginPage.vue'),
      meta: { guestOnly: true },
    },
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
      component: () => import('./pages/LinksPage.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/bookmarks',
      name: 'bookmarks',
      component: () => import('./pages/BookmarksPage.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/admin',
      name: 'admin',
      component: () => import('./pages/AdminPage.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: () => import('./pages/NotFoundPage.vue'),
    },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()

  if (!auth.isAuthenticated && !to.meta.guestOnly) {
    await auth.loadUser()
  }

  if (to.meta.guestOnly) {
    if (auth.isAuthenticated) return { name: 'home' }
    return true
  }

  if (to.meta.requiresAuth) {
    if (!auth.isAuthenticated) {
      auth.redirectToLogin(to.fullPath)
      return false
    }
    if (to.meta.requiresEditor && !auth.isEditor) {
      return { name: 'home' }
    }
    if (to.meta.requiresAdmin && !auth.isAdmin) {
      return { name: 'home' }
    }
  }

  return true
})
