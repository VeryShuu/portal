import http from 'k6/http'
import { check, sleep } from 'k6'

const BASE = __ENV.BASE_URL || 'http://localhost:8000'

export const options = {
  stages: [
    { duration: '15s', target: 50 },
    { duration: '30s', target: 50 },
    { duration: '10s', target: 0 },
  ],
  thresholds: {
    http_req_duration: ['p(95)<2000'],   // ТЗ §7: p95 < 2 сек
    http_req_failed: ['rate<0.02'],
  },
}

export default function () {
  const responses = http.batch([
    ['GET', `${BASE}/health`],
    ['GET', `${BASE}/ready`],
  ])
  for (const r of responses) {
    check(r, { 'status<500': (resp) => resp.status < 500 })
  }
  sleep(1)
}
