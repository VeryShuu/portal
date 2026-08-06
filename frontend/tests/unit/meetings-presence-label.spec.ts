import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string, params?: Record<string, unknown>) => {
    if (params && k.includes('until')) return `${k}:${JSON.stringify(params)}`
    return k
  }, locale: { value: 'ru' } }),
  createI18n: () => ({ global: { t: (k: string) => k, locale: { value: 'ru' } } }),
}))

import { usePresenceLabel } from '../../src/composables/usePresenceLabel'
import type { InvitedAbsence } from '../../src/api/meetings'

describe('usePresenceLabel', () => {
  const Harness = defineComponent({
    props: { absence: { type: Object as () => InvitedAbsence | null, default: null } },
    setup(props) {
      const { presenceLabel, presenceClass } = usePresenceLabel()
      return () => h('div', [
        h('span', { class: 'label' }, presenceLabel(props.absence)),
        h('span', { class: 'cls' }, presenceClass(props.absence)),
      ])
    },
  })

  const mountHarness = (absence: InvitedAbsence | null) =>
    mount(Harness, { props: { absence } })

  it('returns empty label and class when absence is null', () => {
    const w = mountHarness(null)
    expect(w.find('.label').text()).toBe('')
    expect(w.find('.cls').text()).toBe('')
  })

  it('returns category label with date suffix', () => {
    const w = mountHarness({
      category: 'vacation', start_date: '2026-08-10', end_date: '2026-08-15',
    })
    expect(w.find('.label').text()).toContain('users.presence.vacation')
    expect(w.find('.label').text()).toContain('users.presence.until')
  })

  it('returns category class', () => {
    const w = mountHarness({
      category: 'sick', start_date: '2026-08-06', end_date: '2026-08-09',
    })
    expect(w.find('.cls').text()).toBe('presence--sick')
  })

  it('handles business_trip category', () => {
    const w = mountHarness({
      category: 'business_trip', start_date: '2026-08-06', end_date: '2026-08-10',
    })
    expect(w.find('.label').text()).toContain('users.presence.business_trip')
    expect(w.find('.cls').text()).toBe('presence--business_trip')
  })
})
