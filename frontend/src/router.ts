import { createRouter, createWebHistory, type RouteLocationNormalized, type RouteLocationRaw } from 'vue-router'
import { useAuthStore } from './stores/auth'
import { useModulesStore } from './stores/modules'
import AppLayout from './components/AppLayout.vue'

export const ROUTES = {
  HOME: '/',
  NEWS: '/news',
  KB: '/kb',
  FILES: '/files',
  LINKS: '/links',
  BOOKMARKS: '/bookmarks',
  PROFILE: '/profile',
  MY_FEEDBACK: '/my-feedback',
  SETTINGS: '/settings',
  ADMIN: '/admin',
  TRASH: '/trash',
  STAFF: '/staff',
  PHOTOS: '/photos',
  PHOTOS_MY_SHARES: '/photos/my-shares',
  PHOTOS_PUBLIC_FOLDER: '/photos/public/:token',
  PHOTOS_PUBLIC_PHOTO: '/p/:token',
  LOGIN: '/login',
  AUTH_LOCAL: '/auth/local',
  AUTH_ERROR: '/auth/error',
  AUTH_CALLBACK: '/auth/callback',
} as const

export const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: ROUTES.LOGIN,
      name: 'login',
      component: () => import('./pages/AuthRedirectStub.vue'),
      meta: { public: true },
    },
    {
      path: ROUTES.AUTH_LOCAL,
      name: 'auth-local',
      component: () => import('./pages/AuthLocalPage.vue'),
      meta: { public: true },
    },
    {
      path: ROUTES.AUTH_ERROR,
      name: 'auth-error',
      component: () => import('./pages/AuthErrorPage.vue'),
      meta: { public: true },
    },
    {
      path: ROUTES.AUTH_CALLBACK,
      name: 'auth-callback',
      component: () => import('./pages/AuthCallbackPage.vue'),
      meta: { public: true },
    },
    {
      path: ROUTES.PHOTOS_PUBLIC_PHOTO,
      name: 'public-photo',
      component: () => import('./pages/photos/PublicPhotoPage.vue'),
      meta: { guestOnly: false, requiresAuth: false, public: true },
    },
    {
      path: ROUTES.PHOTOS_PUBLIC_FOLDER,
      name: 'public-folder',
      component: () => import('./pages/photos/PublicFolderPage.vue'),
      meta: { requiresAuth: false, public: true },
    },
    {
      path: ROUTES.HOME,
      component: AppLayout,
      meta: { requiresAuth: true },
      children: [
        {
          path: '',
          name: 'home',
          component: () => import('./pages/HomePage.vue'),
        },
        {
          path: ROUTES.NEWS,
          name: 'news-list',
          component: () => import('./pages/NewsListPage.vue'),
        },
        {
          path: `${ROUTES.NEWS}/create`,
          name: 'news-create',
          component: () => import('./pages/NewsFormPage.vue'),
          meta: { requiresEditor: true },
        },
        {
          path: `${ROUTES.NEWS}/:id`,
          name: 'news-detail',
          component: () => import('./pages/NewsDetailPage.vue'),
        },
        {
          path: `${ROUTES.NEWS}/:id/edit`,
          name: 'news-edit',
          component: () => import('./pages/NewsFormPage.vue'),
          meta: { requiresEditor: true },
        },
        {
          path: ROUTES.PROFILE,
          name: 'profile',
          component: () => import('./pages/UserProfileView.vue'),
        },
        {
          path: '/users/:id',
          name: 'user-profile',
          component: () => import('./pages/UserProfileView.vue'),
        },
        {
          path: ROUTES.KB,
          name: 'kb',
          component: () => import('./pages/KbListPage.vue'),
        },
        {
          path: `${ROUTES.KB}/create`,
          name: 'kb-create',
          component: () => import('./pages/KbArticleFormPage.vue'),
        },
        {
          path: `${ROUTES.KB}/articles/:id`,
          name: 'kb-article',
          component: () => import('./pages/KbArticlePage.vue'),
        },
        {
          path: `${ROUTES.KB}/articles/:id/edit`,
          name: 'kb-article-edit',
          component: () => import('./pages/KbArticleFormPage.vue'),
        },
        {
          path: ROUTES.PHOTOS,
          name: 'photos',
          component: () => import('./pages/photos/PhotosIndexPage.vue'),
        },
        {
          path: ROUTES.PHOTOS_MY_SHARES,
          name: 'photos-my-shares',
          component: () => import('./pages/photos/MySharesPage.vue'),
        },
        {
          path: ROUTES.FILES,
          name: 'files',
          component: () => import('./pages/FilesPage.vue'),
        },
        {
          path: ROUTES.LINKS,
          name: 'links',
          component: () => import('./pages/LinksAndBookmarksPage.vue'),
        },
        {
          path: ROUTES.STAFF,
          name: 'staff',
          component: () => import('./pages/StaffDirectoryPage.vue'),
          meta: { title: 'nav.staff' },
        },
        {
          path: ROUTES.BOOKMARKS,
          redirect: { name: 'links', query: { tab: 'my' } },
        },
        {
          path: ROUTES.MY_FEEDBACK,
          name: 'my-feedback',
          component: () => import('./pages/MyFeedbackPage.vue'),
          meta: { requiresAuth: true },
        },
        {
          path: ROUTES.SETTINGS,
          name: 'settings',
          component: () => import('./pages/SettingsPage.vue'),
          meta: { requiresEditor: true },
        },
        {
          path: ROUTES.ADMIN,
          name: 'admin',
          component: () => import('./pages/AdminPage.vue'),
          meta: { requiresAdmin: true },
        },
        {
          path: ROUTES.TRASH,
          name: 'trash',
          component: () => import('./pages/TrashPage.vue'),
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

// ── Guards (composed in beforeEach below) ────────────────────────────────────
// Each guard handles a single concern and returns either a NavigationResult
// (RouteLocationRaw / false) to short-circuit, or `null` to continue.

type RouteTo = RouteLocationNormalized
type GuardOutcome = RouteLocationRaw | false | null

async function requireAuth(to: RouteTo): Promise<GuardOutcome> {
  const auth = useAuthStore()

  if (!auth.isAuthenticated && !to.meta.public) {
    const result = await auth.loadBootstrap()
    if (result === 'network_error' && to.meta.requiresAuth) {
      return { name: 'auth-error' }
    }
  }

  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    if (!auth.backendDown) auth.redirectToSSO(to.fullPath)
    return false
  }

  return null
}

function requireRole(to: RouteTo): GuardOutcome {
  if (!to.meta.requiresAuth) return null
  const auth = useAuthStore()

  if (to.meta.requiresEditor && !auth.isEditor) return { name: 'home' }
  if (to.meta.requiresAdmin && !auth.isAdmin) return { name: 'home' }

  return null
}

const MODULE_ROUTES: ReadonlyArray<{
  prefix: string
  module: 'nextcloud' | 'photos'
}> = [
  { prefix: ROUTES.FILES, module: 'nextcloud' },
  { prefix: ROUTES.PHOTOS, module: 'photos' },
]

async function requireModule(to: RouteTo): Promise<GuardOutcome> {
  const auth = useAuthStore()
  if (!auth.isAuthenticated) return null

  const match = MODULE_ROUTES.find(
    ({ prefix }) => to.path === prefix || to.path.startsWith(`${prefix}/`),
  )
  if (!match) return null

  const modulesStore = useModulesStore()
  try {
    await modulesStore.load()
  } catch {
    // Fail-closed: if modules info cannot be loaded and we have no cached
    // data, isEnabled() returns false and the user is redirected home.
  }
  if (!modulesStore.isEnabled(match.module)) return { name: 'home' }
  return null
}

router.beforeEach(async (to) => {
  const authResult = await requireAuth(to)
  if (authResult !== null) return authResult

  const roleResult = requireRole(to)
  if (roleResult !== null) return roleResult

  const moduleResult = await requireModule(to)
  if (moduleResult !== null) return moduleResult

  return true
})
