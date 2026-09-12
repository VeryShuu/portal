/**
 * API публичного контура обучения: /auth/learning/* (ADR-051).
 * Отдельный модуль (не api/learning.ts), чтобы эти вызовы не попадали
 * в портал-бандл — там они не нужны.
 *
 * Passwordless-вход (миграция 113): шаг 1 — запрос кода на email, шаг 2 —
 * сверка кода. Cookie `learning_session` ставит backend (HTTPOnly);
 * XSRF-токен ходит через общий перехватчик api/index (double-submit).
 */
import { api } from './index'

export function learningRequestCode(email: string) {
  return api<{ ok: boolean }>('/auth/learning/login', {
    method: 'POST',
    body: { email },
  })
}

export function learningVerifyCode(email: string, code: string) {
  return api<{ ok: boolean }>('/auth/learning/verify', {
    method: 'POST',
    body: { email, code },
  })
}

export function learnerLogout() {
  return api<{ ok: boolean }>('/auth/learning/logout', { method: 'POST' })
}
