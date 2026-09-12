/**
 * ApprovalsTab.vue (простая обёртка) + onToggleApprovals/goToApprovals в
 * useModulesState (тумблер модуля в «Модулях»).
 */
import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

// ── ApprovalsTab ────────────────────────────────────────────────────────────

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

vi.mock('../../src/components/admin/ApprovalsSettings.vue', () => ({
  default: { template: '<section class="approvals-settings-stub" />' },
}))

import ApprovalsTab from '../../src/pages/admin/tabs/ApprovalsTab.vue'

describe('ApprovalsTab.vue', () => {
  it('рендерит ApprovalsSettings', async () => {
    const w = mount(ApprovalsTab, { global: { plugins: [i18n] } })
    await flushPromises()
    expect(w.find('.approvals-settings-stub').exists()).toBe(true)
  })
})

