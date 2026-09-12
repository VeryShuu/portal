import { describe, it, expect, vi } from 'vitest'

vi.mock('../../src/api/index', () => ({
  api: vi.fn().mockResolvedValue({ id: 'u1' }),
  apiUpload: vi.fn().mockResolvedValue({ id: 'u1' }),
  BASE_URL: '/api/v1',
}))

import { deleteAvatar, adminUploadUserAvatar, adminDeleteUserAvatar } from '../../src/api/users'
import { api, apiUpload } from '../../src/api/index'

describe('users API — аватары', () => {
  it('deleteAvatar → DELETE /users/me/avatar', async () => {
    await deleteAvatar()
    expect(api).toHaveBeenCalledWith('/users/me/avatar', { method: 'DELETE' })
  })

  it('adminUploadUserAvatar → multipart POST admin-эндпоинта', async () => {
    const file = new File(['x'], 'a.png', { type: 'image/png' })
    await adminUploadUserAvatar('uid-1', file)
    expect(apiUpload).toHaveBeenCalledWith('/users/admin/uid-1/avatar', expect.any(FormData))
    const form = (apiUpload as ReturnType<typeof vi.fn>).mock.calls[0][1] as FormData
    expect(form.get('file')).toBe(file)
  })

  it('adminDeleteUserAvatar → DELETE admin-эндпоинта', async () => {
    await adminDeleteUserAvatar('uid-1')
    expect(api).toHaveBeenCalledWith('/users/admin/uid-1/avatar', { method: 'DELETE' })
  })
})
