/**
 * API-клиент Directum: пути/методы/query-параметры всех функций.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('../../src/api/index', () => ({ api: vi.fn() }))

import { api } from '../../src/api/index'
import {
  fetchDirectumSettings,
  putDirectumSettings,
  testDirectumConnection,
  runDirectumNow,
  fetchDirectumRuns,
} from '../../src/api/directum'

const apiMock = api as unknown as ReturnType<typeof vi.fn>

describe('api/directum', () => {
  beforeEach(() => {
    apiMock.mockReset().mockResolvedValue({})
  })

  it('GET settings', async () => {
    await fetchDirectumSettings()
    expect(apiMock).toHaveBeenCalledWith('/directum/settings')
  })

  it('PUT settings с телом', async () => {
    const dto = { enabled: true } as Parameters<typeof putDirectumSettings>[0]
    await putDirectumSettings(dto)
    expect(apiMock).toHaveBeenCalledWith('/directum/settings', { method: 'PUT', body: dto })
  })

  it('POST test', async () => {
    await testDirectumConnection()
    expect(apiMock).toHaveBeenCalledWith('/directum/test', { method: 'POST' })
  })

  it('POST run', async () => {
    await runDirectumNow()
    expect(apiMock).toHaveBeenCalledWith('/directum/run', { method: 'POST' })
  })

  it('GET runs с limit/offset', async () => {
    await fetchDirectumRuns({ limit: 50, offset: 100 })
    expect(apiMock).toHaveBeenCalledWith('/directum/runs', { query: { limit: 50, offset: 100 } })
  })

  it('GET runs без параметров — пустой query', async () => {
    await fetchDirectumRuns()
    expect(apiMock).toHaveBeenCalledWith('/directum/runs', { query: {} })
  })
})
