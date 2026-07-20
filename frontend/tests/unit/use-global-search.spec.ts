import { describe, it, expect, beforeEach, vi } from 'vitest'

const fetchNewsListMock = vi.fn()
const globalSearchMock = vi.fn()
const fetchUsersMock = vi.fn()

vi.mock('../../src/api/news', () => ({
  fetchNewsList: (...args: unknown[]) => fetchNewsListMock(...args),
}))
vi.mock('../../src/api/kb', () => ({
  globalSearch: (...args: unknown[]) => globalSearchMock(...args),
}))
vi.mock('../../src/api/users', () => ({
  fetchUsers: (...args: unknown[]) => fetchUsersMock(...args),
}))

import { runGlobalSearch } from '../../src/composables/useGlobalSearch'

describe('useGlobalSearch (src/composables)', () => {
  beforeEach(() => {
    fetchNewsListMock.mockClear()
    globalSearchMock.mockClear()
    fetchUsersMock.mockClear()
  })

  it('aggregates fulfilled results from all three sources, slicing to per-source limits', async () => {
    fetchNewsListMock.mockResolvedValue({ items: [{ id: 'n1' }, { id: 'n2' }] })
    globalSearchMock.mockResolvedValue({
      items: [
        { type: 'article', id: 'a1' },
        { type: 'section', id: 's1' },
        { type: 'article', id: 'a2' },
      ],
    })
    fetchUsersMock.mockResolvedValue({ items: [{ id: 'u1' }, { id: 'u2' }, { id: 'u3' }] })

    const res = await runGlobalSearch('q', { newsLimit: 5, kbLimit: 5, userLimit: 2 })

    expect(res.news).toHaveLength(2)
    expect(res.kb).toEqual([{ type: 'article', id: 'a1' }, { type: 'article', id: 'a2' }])
    expect(res.users).toHaveLength(2)

    // Signal is forwarded to each underlying call.
    const controller = new AbortController()
    await runGlobalSearch('q', { newsLimit: 1, kbLimit: 1, userLimit: 1, signal: controller.signal })
    const newsCall = fetchNewsListMock.mock.calls.at(-1)!
    expect(newsCall[1]).toEqual({ signal: controller.signal })
  })

  it('returns empty array for sources whose promise rejects', async () => {
    fetchNewsListMock.mockRejectedValue(new Error('boom'))
    globalSearchMock.mockResolvedValue({ items: [{ type: 'article', id: 'a1' }] })
    fetchUsersMock.mockRejectedValue(new Error('boom'))

    const res = await runGlobalSearch('q', { newsLimit: 5, kbLimit: 5, userLimit: 5 })

    expect(res.news).toEqual([])
    expect(res.kb).toEqual([{ type: 'article', id: 'a1' }])
    expect(res.users).toEqual([])
  })
})
