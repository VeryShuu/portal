/**
 * Прицельная нагрузка на поиск (ТЗ: поиск < 1 сек).
 */
import http from 'k6/http'
import { check } from 'k6'

const BASE = __ENV.BASE_URL || 'http://localhost:8000'

const QUERIES = ['отчёт', 'инструкция', 'регламент', 'kpi', 'политика', 'договор', 'безопасность']

export const options = {
  vus: 50,
  duration: '1m',
  thresholds: {
    http_req_duration: ['p(95)<1000', 'p(99)<1500'],
    http_req_failed: ['rate<0.02'],
  },
}

export default function () {
  const q = QUERIES[Math.floor(Math.random() * QUERIES.length)]
  const r = http.get(`${BASE}/api/v1/search?q=${encodeURIComponent(q)}`, {
    headers: { Origin: BASE },
  })
  check(r, { 'status < 500': (resp) => resp.status < 500 })
}
