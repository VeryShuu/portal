import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.fn()

vi.mock('../../src/api/index', () => ({
  api: (...args: unknown[]) => apiMock(...args),
}))

import {
  fetchSignatureConfig,
  generateSignature,
  fetchSignatureSettings,
  updateSignatureSettings,
  type SignatureGenerateRequest,
  type SignatureSettings,
} from '../../src/api/signature'

describe('signature API client', () => {
  beforeEach(() => {
    apiMock.mockReset()
    apiMock.mockResolvedValue({})
  })

  it('fetchSignatureConfig GETs /signature/config', async () => {
    await fetchSignatureConfig()
    expect(apiMock).toHaveBeenCalledWith('/signature/config')
  })

  it('generateSignature POSTs body', async () => {
    const body: SignatureGenerateRequest = {
      name: 'Ivan',
      surname: 'Petrov',
      position: 'Engineer',
      language: 'Ru',
      device: 'PC',
      city_id: 1,
      office_phone: '+7 (8152) 400 580',
      extension: '123',
      mobile_phone: null,
      email: 'ivan@mage.ru',
    }
    await generateSignature(body)
    expect(apiMock).toHaveBeenCalledWith('/signature/generate', {
      method: 'POST',
      body,
    })
  })

  it('fetchSignatureSettings GETs admin settings', async () => {
    await fetchSignatureSettings()
    expect(apiMock).toHaveBeenCalledWith('/signature/admin/settings')
  })

  it('updateSignatureSettings PUTs admin settings', async () => {
    const settings: SignatureSettings = {
      cities: [],
      office_phones: ['+7'],
      support_email: 'it@mage.ru',
      company_url: 'http://mage.ru/',
      logo_base_url: 'http://mage.ru/signature/images/',
      attr_mobile: 'mobile',
      attr_office_phone: 'telephoneNumber',
      attr_city: 'city',
    }
    await updateSignatureSettings(settings)
    expect(apiMock).toHaveBeenCalledWith('/signature/admin/settings', {
      method: 'PUT',
      body: settings,
    })
  })
})
