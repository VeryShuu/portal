import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

const mockApi = vi.fn()
vi.mock('../../src/api/index', () => ({ api: mockApi }))

vi.mock('../../src/styles/naive-theme', () => ({
  lightThemeOverrides: { common: {}, Menu: {} },
  darkThemeOverrides: { common: {}, Menu: {} },
}))

const mockSetProperty = vi.fn()
const mockDocumentTitle = { value: '' }

Object.defineProperty(document, 'title', {
  get: () => mockDocumentTitle.value,
  set: (v) => { mockDocumentTitle.value = v },
  configurable: true,
})
Object.defineProperty(document, 'documentElement', {
  value: { style: { setProperty: mockSetProperty } },
  configurable: true,
})

describe('useBrandingStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    mockApi.mockReset()
  })

  describe('isBannerActive', () => {
    it('is false when banner_enabled=false', async () => {
      const { useBrandingStore } = await import('../../src/stores/branding')
      const store = useBrandingStore()
      store.settings.banner_enabled = false
      store.settings.banner_text = 'Hello'
      expect(store.isBannerActive).toBe(false)
    })

    it('is false when banner_text is empty', async () => {
      const { useBrandingStore } = await import('../../src/stores/branding')
      const store = useBrandingStore()
      store.settings.banner_enabled = true
      store.settings.banner_text = ''
      expect(store.isBannerActive).toBe(false)
    })

    it('is true when enabled, text set, no expiry', async () => {
      const { useBrandingStore } = await import('../../src/stores/branding')
      const store = useBrandingStore()
      store.settings.banner_enabled = true
      store.settings.banner_text = 'Info'
      store.settings.banner_expires_at = null
      expect(store.isBannerActive).toBe(true)
    })

    it('is false when expiry is in the past', async () => {
      const { useBrandingStore } = await import('../../src/stores/branding')
      const store = useBrandingStore()
      store.settings.banner_enabled = true
      store.settings.banner_text = 'Expired'
      store.settings.banner_expires_at = '2000-01-01T00:00:00Z'
      expect(store.isBannerActive).toBe(false)
    })

    it('is true when expiry is in the future', async () => {
      const { useBrandingStore } = await import('../../src/stores/branding')
      const store = useBrandingStore()
      store.settings.banner_enabled = true
      store.settings.banner_text = 'Active'
      store.settings.banner_expires_at = '2099-01-01T00:00:00Z'
      expect(store.isBannerActive).toBe(true)
    })
  })

  describe('accent computed', () => {
    it('returns base/hover/pressed for valid hex', async () => {
      const { useBrandingStore } = await import('../../src/stores/branding')
      const store = useBrandingStore()
      store.settings.accent_color = '#d8262c'
      expect(store.accent.base).toBe('#d8262c')
      expect(typeof store.accent.hover).toBe('string')
      expect(typeof store.accent.pressed).toBe('string')
    })

    it('returns fallback for invalid hex', async () => {
      const { useBrandingStore } = await import('../../src/stores/branding')
      const store = useBrandingStore()
      store.settings.accent_color = 'not-a-color'
      expect(store.accent.base).toBe('not-a-color')
      expect(store.accent.hover).toBe('not-a-color')
    })
  })

  describe('lightOverrides / darkOverrides', () => {
    it('lightOverrides includes primaryColor from accent', async () => {
      const { useBrandingStore } = await import('../../src/stores/branding')
      const store = useBrandingStore()
      store.settings.accent_color = '#ff0000'
      expect(store.lightOverrides.common?.primaryColor).toBe('#ff0000')
    })

    it('darkOverrides includes primaryColor from accent', async () => {
      const { useBrandingStore } = await import('../../src/stores/branding')
      const store = useBrandingStore()
      store.settings.accent_color = '#00ff00'
      expect(store.darkOverrides.common?.primaryColor).toBe('#00ff00')
    })
  })

  describe('load()', () => {
    it('merges api response with defaults', async () => {
      const { useBrandingStore } = await import('../../src/stores/branding')
      mockApi.mockResolvedValueOnce({ portal_name: 'MyPortal', accent_color: '#123456' })
      const store = useBrandingStore()
      await store.load()
      expect(store.settings.portal_name).toBe('MyPortal')
      expect(store.settings.accent_color).toBe('#123456')
      expect(store.loaded).toBe(true)
    })

    it('uses defaults on api error', async () => {
      const { useBrandingStore } = await import('../../src/stores/branding')
      mockApi.mockRejectedValueOnce(new Error('network'))
      const store = useBrandingStore()
      await store.load()
      expect(store.settings.portal_name).toBe('Корпоративный портал')
      expect(store.loaded).toBe(true)
    })

    it('sets document.title to portal_name', async () => {
      const { useBrandingStore } = await import('../../src/stores/branding')
      mockApi.mockResolvedValueOnce({ portal_name: 'TestPortal' })
      const store = useBrandingStore()
      await store.load()
      expect(document.title).toBe('TestPortal')
    })
  })

  describe('save()', () => {
    it('updates settings on success', async () => {
      const { useBrandingStore } = await import('../../src/stores/branding')
      const saved = { portal_name: 'New', accent_color: '#abcdef', portal_tagline: '',
        banner_enabled: false, banner_text: '', banner_type: 'info' as const, banner_expires_at: null }
      mockApi.mockResolvedValueOnce(saved)
      const store = useBrandingStore()
      await store.save({ portal_name: 'New' })
      expect(store.settings.portal_name).toBe('New')
    })

    it('rolls back settings on api error', async () => {
      const { useBrandingStore } = await import('../../src/stores/branding')
      mockApi.mockRejectedValueOnce(new Error('save failed'))
      const store = useBrandingStore()
      const original = store.settings.portal_name
      await expect(store.save({ portal_name: 'ShouldNotStick' })).rejects.toThrow()
      expect(store.settings.portal_name).toBe(original)
    })
  })
})
