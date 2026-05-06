import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from './stores/auth'
import { useModulesStore } from './stores/modules'
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
      path: '/p/:token',
      name: 'public-photo',
      component: () => import('./pages/photos/PublicPhotoPage.vue'),
      meta: { guestOnly: false, requiresAuth: false, public: true },
    },
    {
      path: '/photos/public/:token',
      name: 'public-folder',
      component: () => import('./pages/photos/PublicFolderPage.vue'),
      meta: { requiresAuth: false, public: true },
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
          path: 'users/:id',
          name: 'user-profile',
          component: () => import('./pages/UserProfileViewPage.vue'),
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
        },
        {
          path: 'photos',
          name: 'photos',
          component: () => import('./pages/photos/PhotosIndexPage.vue'),
        },
        {
          path: 'photos/my-shares',
          name: 'photos-my-shares',
          component: () => import('./pages/photos/MySharesPage.vue'),
        },
        {
          path: 'files',
          name: 'files',
          component: () => import('./pages/FilesPage.vue'),
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
        {
          path: ':pathMatch(.*)*',
          name: 'not-found',
          component: () => import('./pages/NotFoundPage.vue'),
        },
      ],
    },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()

  if (!auth.isAuthenticated && !to.meta.guestOnly && !to.meta.public) {
    const result = await auth.loadUser()
    if (result === 'network_error' && to.meta.requiresAuth) {
      return { name: 'home' }
    }
  }

  if (to.meta.guestOnly) {
    if (auth.isAuthenticated) return { name: 'home' }
    return true
  }

  if (to.meta.requiresAuth) {
    if (!auth.isAuthenticated) {
      if (!auth.backendDown) {
        auth.redirectToLogin(to.fullPath)
      }
      return false
    }
    if (to.meta.requiresEditor && !auth.isEditor) {
      return { name: 'home' }
    }
    if (to.meta.requiresAdmin && !auth.isAdmin) {
      return { name: 'home' }
    }
  }

  if (auth.isAuthenticated) {
    const needsModuleCheck =
      to.path === '/files' || to.path.startsWith('/files/') ||
      to.path === '/photos' || to.path.startsWith('/photos/')

    if (needsModuleCheck) {
      const modulesStore = useModulesStore()
      try {
        await modulesStore.load()
      } catch {
        // On load failure treat modules as enabled (fail-open) to avoid blocking navigation
      }
      if (
        (to.path === '/files' || to.path.startsWith('/files/')) &&
        !modulesStore.isEnabled('nextcloud')
      ) {
        return { name: 'home' }
      }
      if (
        (to.path === '/photos' || to.path.startsWith('/photos/')) &&
        !modulesStore.isEnabled('photos')
      ) {
        return { name: 'home' }
      }
    }
  }

  return true
})
