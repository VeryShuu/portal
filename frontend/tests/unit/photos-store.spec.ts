import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

const mockFetchRecentPhotos = vi.fn()

vi.mock('../../src/api/photos', () => ({
  fetchRecentPhotos: mockFetchRecentPhotos,
}))

describe('usePhotosStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  describe('initial state', () => {
    it('recent is empty', async () => {
      const { usePhotosStore } = await import('../../src/stores/photos')
      const store = usePhotosStore()
      expect(store.recent).toHaveLength(0)
    })

    it('recentLoaded is false', async () => {
      const { usePhotosStore } = await import('../../src/stores/photos')
      const store = usePhotosStore()
      expect(store.recentLoaded).toBe(false)
    })

    it('recentLoading is false', async () => {
      const { usePhotosStore } = await import('../../src/stores/photos')
      const store = usePhotosStore()
      expect(store.recentLoading).toBe(false)
    })

    it('configured is true by default', async () => {
      const { usePhotosStore } = await import('../../src/stores/photos')
      const store = usePhotosStore()
      expect(store.configured).toBe(true)
    })
  })

  describe('loadRecent()', () => {
    it('populates recent on success', async () => {
      const { usePhotosStore } = await import('../../src/stores/photos')
      const photos = [
        { id: '1', url: '/photos/1.jpg', thumbnail_url: '/photos/1_thumb.jpg', folder_id: 'f1', taken_at: '', created_at: '' },
        { id: '2', url: '/photos/2.jpg', thumbnail_url: '/photos/2_thumb.jpg', folder_id: 'f1', taken_at: '', created_at: '' },
      ]
      mockFetchRecentPhotos.mockResolvedValueOnce(photos)

      const store = usePhotosStore()
      await store.loadRecent()

      expect(store.recent).toEqual(photos)
      expect(store.recentLoaded).toBe(true)
      expect(store.recentLoading).toBe(false)
      expect(store.configured).toBe(true)
    })

    it('sets recentLoaded=true and recentLoading=false after success', async () => {
      const { usePhotosStore } = await import('../../src/stores/photos')
      mockFetchRecentPhotos.mockResolvedValueOnce([])

      const store = usePhotosStore()
      await store.loadRecent()

      expect(store.recentLoaded).toBe(true)
      expect(store.recentLoading).toBe(false)
    })

    it('passes limit to api call', async () => {
      const { usePhotosStore } = await import('../../src/stores/photos')
      mockFetchRecentPhotos.mockResolvedValueOnce([])

      const store = usePhotosStore()
      await store.loadRecent(4)

      expect(mockFetchRecentPhotos).toHaveBeenCalledWith(4)
    })

    it('uses default limit of 8', async () => {
      const { usePhotosStore } = await import('../../src/stores/photos')
      mockFetchRecentPhotos.mockResolvedValueOnce([])

      const store = usePhotosStore()
      await store.loadRecent()

      expect(mockFetchRecentPhotos).toHaveBeenCalledWith(8)
    })

    it('on error sets configured=false and clears recent', async () => {
      const { usePhotosStore } = await import('../../src/stores/photos')
      mockFetchRecentPhotos.mockRejectedValueOnce(new Error('network error'))

      const store = usePhotosStore()
      store.recent = [{ id: '1' } as any]
      await store.loadRecent()

      expect(store.configured).toBe(false)
      expect(store.recent).toHaveLength(0)
      expect(store.recentLoaded).toBe(true)
      expect(store.recentLoading).toBe(false)
    })

    it('does not call api if already loading', async () => {
      const { usePhotosStore } = await import('../../src/stores/photos')

      let resolve!: (v: any[]) => void
      mockFetchRecentPhotos.mockReturnValueOnce(new Promise(r => { resolve = r }))

      const store = usePhotosStore()
      const first = store.loadRecent()
      store.loadRecent()

      resolve([])
      await first

      expect(mockFetchRecentPhotos).toHaveBeenCalledTimes(1)
    })
  })
})
