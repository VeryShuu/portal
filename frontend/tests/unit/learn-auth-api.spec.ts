import { describe, it, expect, vi, beforeEach } from 'vitest'

/**
 * Транспортный спек learn-авторизации (ADR-051): реальные функции
 * api/learningAuth с моком только транспортного слоя api/index.
 * Пути/методы/тела — контракт /auth/learning/* (passwordless, миграция 113).
 */

const mockApi = vi.fn()
vi.mock('../../src/api/index', () => ({
  api: (...a: unknown[]) => mockApi(...(a as [])),
  apiUpload: vi.fn(),
  BASE_URL: '/api/v1',
}))

import {
  learningRequestCode,
  learningVerifyCode,
  learnerLogout,
} from '../../src/api/learningAuth'

beforeEach(() => {
  mockApi.mockReset()
  mockApi.mockResolvedValue({ ok: true })
})

describe('api/learningAuth: контракты вызовов', () => {
  it('запрос кода: POST email (шаг 1)', async () => {
    await learningRequestCode('a@b.ru')
    expect(mockApi).toHaveBeenCalledWith('/auth/learning/login', {
      method: 'POST',
      body: { email: 'a@b.ru' },
    })
  })

  it('verify: POST email+code (шаг 2)', async () => {
    await learningVerifyCode('a@b.ru', '123456')
    expect(mockApi).toHaveBeenCalledWith('/auth/learning/verify', {
      method: 'POST',
      body: { email: 'a@b.ru', code: '123456' },
    })
  })

  it('logout: POST без тела', async () => {
    await learnerLogout()
    expect(mockApi).toHaveBeenCalledWith('/auth/learning/logout', { method: 'POST' })
  })
})
