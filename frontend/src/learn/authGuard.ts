/**
 * Реакция learn-контура на истечение learner-сессии: api/index на 401
 * диспатчит `auth:expired` и (в отличие от портала) НЕ редиректит сам —
 * Keycloak/портал-SKO на learn-домене отсутствуют (ADR-051). Здесь мы
 * ведём обучаемого на форму входа, сохраняя целевой маршрут для возврата.
 */
import type { Router } from 'vue-router'

const PUBLIC_ROUTE_NAMES = new Set(['learn-login'])

export function listenAuthExpired(router: Router): () => void {
  const handler = () => {
    const current = router.currentRoute.value
    if (current.name && PUBLIC_ROUTE_NAMES.has(String(current.name))) return
    const target = current.fullPath && current.fullPath !== '/' ? current.fullPath : '/courses'
    void router.push({ name: 'learn-login', query: { redirect: target } })
  }
  window.addEventListener('auth:expired', handler)
  return () => window.removeEventListener('auth:expired', handler)
}
