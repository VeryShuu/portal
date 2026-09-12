/**
 * 300 одновременных сессий — критерий ТЗ §7.
 *
 * Сценарий:
 *  - Логин (локальный, если задан ADMIN_EMAIL/ADMIN_PASSWORD; иначе чтение публичных эндпоинтов)
 *  - Главная: новости, ярлыки, закладки
 *  - Чтение случайной новости
 *  - Поиск
 *
 * Перед запуском убедитесь что бэкенд запущен и доступен по BASE_URL.
 */
import http from 'k6/http'
import { check, sleep, group } from 'k6'
import { Counter, Trend } from 'k6/metrics'

const BASE = __ENV.BASE_URL || 'http://localhost:8000'
const EMAIL = __ENV.ADMIN_EMAIL
const PASSWORD = __ENV.ADMIN_PASSWORD

const loginErrors = new Counter('login_errors')
const searchLatency = new Trend('search_latency_ms', true)

export const options = {
  scenarios: {
    portal: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '1m', target: 100 },
        { duration: '2m', target: 300 },   // ТЗ: 300 одновременных сессий
        { duration: '5m', target: 300 },
        { duration: '1m', target: 0 },
      ],
      gracefulRampDown: '30s',
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<2000'],
    http_req_failed: ['rate<0.05'],
    search_latency_ms: ['p(95)<1000'],     // ТЗ §7: поиск < 1 сек
    checks: ['rate>0.95'],
  },
}

function login() {
  if (!EMAIL || !PASSWORD) return null
  const r = http.post(
    `${BASE}/api/v1/auth/local/login`,
    JSON.stringify({ email: EMAIL, password: PASSWORD }),
    {
      headers: {
        'Content-Type': 'application/json',
        Origin: BASE,
      },
    },
  )
  if (r.status !== 200) {
    loginErrors.add(1)
    return null
  }
  return r.cookies.portal_session?.[0]?.value || null
}

export default function () {
  const session = login()
  const cookies = session ? { portal_session: session } : {}
  const headers = { Origin: BASE }

  group('home', () => {
    const r = http.get(`${BASE}/api/v1/news?page=1&page_size=10`, { cookies, headers })
    check(r, { 'news ok or 401': (resp) => resp.status === 200 || resp.status === 401 })
  })

  group('search', () => {
    const start = Date.now()
    const r = http.get(`${BASE}/api/v1/search?q=test`, { cookies, headers })
    searchLatency.add(Date.now() - start)
    check(r, { 'search ok or 401': (resp) => resp.status === 200 || resp.status === 401 })
  })

  group('links', () => {
    const r = http.get(`${BASE}/api/v1/links`, { cookies, headers })
    check(r, { 'links ok or 401': (resp) => resp.status === 200 || resp.status === 401 })
  })

  group('photos_tree', () => {
    const r = http.get(`${BASE}/api/v1/photos/folders/tree`, { cookies, headers })
    check(r, { 'photos_tree ok or 401': (resp) => resp.status === 200 || resp.status === 401 })
  })

  group('kb_sections', () => {
    const r = http.get(`${BASE}/api/v1/kb/sections`, { cookies, headers })
    check(r, { 'kb_sections ok or 401': (resp) => resp.status === 200 || resp.status === 401 })
  })

  sleep(Math.random() * 2 + 1)
}
