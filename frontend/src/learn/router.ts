/**
 * Роутер learn-контура. Имена learning/learning-course/learning-test совпадают
 * с портал-роутером: переиспользуемые страницы курса и теста навигируются
 * по имени (router.push({ name })) и работают в обеих сборках без изменений.
 */
import { createRouter, createWebHistory, type Router } from 'vue-router'

export function createLearnRouter(): Router {
  const router = createRouter({
    history: createWebHistory(),
    routes: [
      {
        path: '/login',
        name: 'learn-login',
        component: () => import('./pages/LearnLoginPage.vue'),
        meta: { public: true },
      },
      // Парольное восстановление упразднено (passwordless, миграция 113):
      // старые ссылки из писем / reset-форм уводим на вход — код придёт заново.
      { path: '/forgot', redirect: { name: 'learn-login' } },
      { path: '/reset', redirect: { name: 'learn-login' } },
      { path: '/reset-password', redirect: { name: 'learn-login' } },
      {
        path: '/courses',
        name: 'learning',
        component: () => import('../pages/learning/LearningPage.vue'),
      },
      {
        path: '/courses/:slug',
        name: 'learning-course',
        component: () => import('../pages/learning/LearnerCoursePage.vue'),
      },
      { path: '/', redirect: { name: 'learning' } },
      { path: '/:pathMatch(.*)*', redirect: { name: 'learning' } },
    ],
  })

  // Защищённые маршруты: без learner-сессии GET /learning/me/* вернёт 401 —
  // api/index диспатчит auth:expired, редирект выполняет listenAuthExpired.
  // Дополнительно login при живой сессии сразу уводит на курсы (проверка
  // внутри самой страницы логина).
  return router
}
