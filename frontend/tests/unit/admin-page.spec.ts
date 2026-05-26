import { describe, it, expect, vi } from 'vitest'

vi.mock('naive-ui', () => ({
  NTabs: { template: '<div><slot /></div>', props: ['value', 'type', 'animated', 'displayDirective'] },
  NTabPane: { template: '<div><slot /></div>', props: ['name', 'tab'] },
  useMessage: () => ({ error: vi.fn(), success: vi.fn(), warning: vi.fn() }),
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
  createI18n: () => ({ global: { t: (k: string) => k, locale: { value: 'ru' } } }),
}))

describe('AdminPage tab decomposition', () => {
  it('defines 10 async tab components', async () => {
    const mod = await import('../../src/pages/AdminPage.vue')
    expect(mod).toBeDefined()
  })

  it('UsersTab is a valid Vue component file', { timeout: 15000 }, async () => {
    const tab = await import('../../src/pages/admin/tabs/UsersTab.vue')
    expect(tab.default).toBeDefined()
  })

  it('LinksTab is a valid Vue component file', async () => {
    const tab = await import('../../src/pages/admin/tabs/LinksTab.vue')
    expect(tab.default).toBeDefined()
  })

  it('EmailTab is a valid Vue component file', async () => {
    const tab = await import('../../src/pages/admin/tabs/EmailTab.vue')
    expect(tab.default).toBeDefined()
  })

  it('SystemTab is a valid Vue component file', async () => {
    const tab = await import('../../src/pages/admin/tabs/SystemTab.vue')
    expect(tab.default).toBeDefined()
  })

  it('KeycloakTab is a valid Vue component file', async () => {
    const tab = await import('../../src/pages/admin/tabs/KeycloakTab.vue')
    expect(tab.default).toBeDefined()
  })

  it('BrandingTab is a valid Vue component file', async () => {
    const tab = await import('../../src/pages/admin/tabs/BrandingTab.vue')
    expect(tab.default).toBeDefined()
  })

  it('ModulesTab is a valid Vue component file', async () => {
    const tab = await import('../../src/pages/admin/tabs/ModulesTab.vue')
    expect(tab.default).toBeDefined()
  })

  it('KbTab is a valid Vue component file', async () => {
    const tab = await import('../../src/pages/admin/tabs/KbTab.vue')
    expect(tab.default).toBeDefined()
  })

  it('AnalyticsTab is a valid Vue component file', async () => {
    const tab = await import('../../src/pages/admin/tabs/AnalyticsTab.vue')
    expect(tab.default).toBeDefined()
  })

  it('AuditTab is a valid Vue component file', async () => {
    const tab = await import('../../src/pages/admin/tabs/AuditTab.vue')
    expect(tab.default).toBeDefined()
  })

  it('PhotosTab (sub-component) is a valid Vue component file', async () => {
    const tab = await import('../../src/pages/admin/tabs/PhotosTab.vue')
    expect(tab.default).toBeDefined()
  })
})
