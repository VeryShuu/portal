import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from './stores/auth'
import AppLayout from './components/AppLayout.vue'

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
      component: AppLayout,
      meta: { requiresAuth: true },
      children: [
        {
          path: '',
          name: 'home',
          component: () => import('./pages/HomePage.vue'),
        },
        {
          path: 'news',
          name: 'news-list',
          component: () => import('./pages/NewsListPage.vue'),
        },
        {
          path: 'news/create',
          name: 'news-create',
          component: () => import('./pages/NewsFormPage.vue'),
          meta: { requiresEditor: true },
        },
        {
          path: 'news/:id',
          name: 'news-detail',
          component: () => import('./pages/NewsDetailPage.vue'),
        },
        {
          path: 'news/:id/edit',
          name: 'news-edit',
          component: () => import('./pages/NewsFormPage.vue'),
          meta: { requiresEditor: true },
        },
        {
          path: 'profile',
          name: 'profile',
          component: () => import('./pages/ProfilePage.vue'),
        },
        {
          path: 'kb',
          name: 'kb',
          component: () => import('./pages/KbListPage.vue'),
        },
        {
          path: 'kb/create',
          name: 'kb-create',
          component: () => import('./pages/KbArticleFormPage.vue'),
          meta: { requiresEditor: true },
        },
        {
          path: 'kb/articles/:id',
          name: 'kb-article',
          component: () => import('./pages/KbArticlePage.vue'),
        },
        {
          path: 'kb/articles/:id/edit',
          name: 'kb-article-edit',
          component: () => import('./pages/KbArticleFormPage.vue'),
          meta: { requiresEditor: true },
        },
        {
          path: 'links',
          name: 'links',
          component: () => import('./pages/LinksPage.vue'),
        },
        {
          path: 'bookmarks',
          name: 'bookmarks',
          component: () => import('./pages/BookmarksPage.vue'),
        },
        {
          path: 'admin',
          name: 'admin',
          component: () => import('./pages/AdminPage.vue'),
          meta: { requiresAdmin: true },
        },
      ],
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
