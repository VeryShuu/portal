import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (k: string, params?: Record<string, unknown>) => {
      if (params && k.includes('until')) return `${k}:${JSON.stringify(params)}`
      return k
    },
    locale: { value: 'ru' },
  }),
  createI18n: () => ({ global: { t: (k: string) => k, locale: { value: 'ru' } } }),
}))

vi.mock('naive-ui', () => ({
  NButton: {
    template: '<button class="n-button" @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'size', 'tertiary', 'quaternary'],
    emits: ['click'],
  },
  NSelect: {
    template: '<select class="n-select" />',
    props: ['value', 'options', 'loading', 'placeholder', 'multiple', 'filterable', 'remote', 'clearFilterAfterSelect', 'renderLabel'],
    emits: ['search', 'update:value'],
  },
  NIcon: { template: '<span class="n-icon"><slot /></span>', props: ['component', 'size'] },
  NTooltip: { template: '<span class="n-tooltip"><slot name="trigger" /><slot /></span>', props: ['trigger', 'placement'] },
  NTag: { template: '<span class="n-tag"><slot /></span>', props: ['size', 'type', 'bordered'] },
  NModal: { template: '<div v-if="show" class="n-modal"><slot /><slot name="footer" /></div>', props: ['show', 'title', 'preset'], emits: ['update:show'] },
  NSpace: { template: '<div class="n-space"><slot /></div>', props: ['justify'] },
}))

vi.mock('../../src/api/meetings', () => ({
  searchParticipants: vi.fn().mockResolvedValue([]),
}))

vi.mock('../../src/composables/useDebounceFn', () => ({
  useDebounceFn: (fn: (q: string) => void) => fn,
}))

vi.mock('../../src/utils/parseApiError', () => ({
  parseApiError: () => 'error',
}))

vi.mock('../../src/components/meetings/PasteParticipantsModal.vue', () => ({
  default: { template: '<div class="paste-modal" />' },
}))

import ParticipantPicker from '../../src/components/meetings/ParticipantPicker.vue'
import type { InvitedUser } from '../../src/api/meetings'

const baseUser = (over: Partial<InvitedUser> = {}): InvitedUser => ({
  user_id: 'u1', full_name: 'Ivanov Ivan', email: 'ivanov@example.com', source: 'keycloak', ...over,
})

const mountPicker = (modelValue: InvitedUser[]) =>
  mount(ParticipantPicker, { props: { modelValue } })

describe('ParticipantPicker.vue — absence presence', () => {
  it('renders presence note when participant has absence', () => {
    const w = mountPicker([
      baseUser({
        absence: { category: 'vacation', start_date: '2026-08-10', end_date: '2026-08-15' },
      }),
    ])
    const presence = w.find('.participant-tag__presence')
    expect(presence.exists()).toBe(true)
    expect(presence.text()).toContain('users.presence.vacation')
    expect(presence.classes()).toContain('presence--vacation')
  })

  it('does not render presence when participant is working', () => {
    const w = mountPicker([baseUser()])
    expect(w.find('.participant-tag__presence').exists()).toBe(false)
  })

  it('does not render presence when absence is null', () => {
    const w = mountPicker([baseUser({ absence: null })])
    expect(w.find('.participant-tag__presence').exists()).toBe(false)
  })

  it('renders sick category with correct class', () => {
    const w = mountPicker([
      baseUser({
        absence: { category: 'sick', start_date: '2026-08-06', end_date: '2026-08-09' },
      }),
    ])
    const presence = w.find('.participant-tag__presence')
    expect(presence.classes()).toContain('presence--sick')
    expect(presence.text()).toContain('users.presence.sick')
  })

  it('renders full name and email alongside presence', () => {
    const w = mountPicker([
      baseUser({
        absence: { category: 'business_trip', start_date: '2026-08-06', end_date: '2026-08-10' },
      }),
    ])
    expect(w.text()).toContain('Ivanov Ivan')
    expect(w.text()).toContain('ivanov@example.com')
    const presence = w.find('.participant-tag__presence')
    expect(presence.classes()).toContain('presence--business_trip')
  })
})
