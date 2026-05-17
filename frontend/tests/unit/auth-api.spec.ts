import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.fn()

vi.mock('../../src/api/index', () => ({
  api: (...args: unknown[]) => apiMock(...args),
}))

import {
  changePassword,
  fetchMe,
  getLoginUrl,
  getLogoutUrl,
  getSSOLoginUrl,
  localLogin,
  refreshSession,
} from '../../src/api/auth'

describe('auth API client', () => {
  beforeEach(() => {
    apiMock.mockReset()
    apiMock.mockResolvedValue(undefined)
  })

  it('fetchMe GETs /auth/me', async () => {
    apiMock.mockResolvedValueOnce({ id: '1', email: 'a@b' })
    const me = await fetchMe()
    expect(apiMock).toHaveBeenCalledWith('/auth/me')
    expect(me.id).toBe('1')
  })

  it('refreshSession POSTs /auth/refresh', async () => {
    await refreshSession()
    expect(apiMock).toHaveBeenCalledWith('/auth/refresh', { method: 'POST' })
  })

  it('localLogin POSTs credentials to /auth/local/login', async () => {
    await localLogin('a@b', 'pw')
    expect(apiMock).toHaveBeenCalledWith('/auth/local/login', {
      method: 'POST',
      body: { email: 'a@b', password: 'pw' },
    })
  })

  it('changePassword PATCHes /users/me/password', async () => {
    await changePassword('old', 'new')
    expect(apiMock).toHaveBeenCalledWith('/users/me/password', {
      method: 'PATCH',
      body: { current_password: 'old', new_password: 'new' },
    })
  })

  it('getSSOLoginUrl encodes redirect target', () => {
    const url = getSSOLoginUrl('/path?x=1&y=2')
    expect(url).toBe('/api/v1/auth/login?redirect=' + encodeURIComponent('/path?x=1&y=2'))
  })

  it('getSSOLoginUrl defaults redirect to /', () => {
    expect(getSSOLoginUrl()).toBe('/api/v1/auth/login?redirect=%2F')
  })

  it('getLoginUrl produces SPA login link with redirect', () => {
    expect(getLoginUrl('/news/1')).toBe('/login?redirect=' + encodeURIComponent('/news/1'))
  })

  it('getLogoutUrl returns fixed logout endpoint', () => {
    expect(getLogoutUrl()).toBe('/api/v1/auth/logout')
  })

  it('fetchMe propagates errors', async () => {
    apiMock.mockRejectedValueOnce(Object.assign(new Error('unauth'), { status: 401 }))
    await expect(fetchMe()).rejects.toMatchObject({ status: 401 })
  })
})
