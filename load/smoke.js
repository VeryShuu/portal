import http from 'k6/http'
import { check, sleep } from 'k6'

const BASE = __ENV.BASE_URL || 'http://localhost:8000'

export const options = {
  vus: 1,
  iterations: 5,
  thresholds: {
    http_req_duration: ['p(95)<1000'],
    http_req_failed: ['rate<0.01'],
    checks: ['rate>0.99'],
  },
}

export default function () {
  const r1 = http.get(`${BASE}/health`)
  check(r1, {
    'health 200': (r) => r.status === 200,
    'security headers': (r) => r.headers['X-Content-Type-Options'] === 'nosniff',
  })

  const r2 = http.get(`${BASE}/ready`)
  check(r2, { 'ready returns json': (r) => r.headers['Content-Type'].includes('json') })

  sleep(0.2)
}
