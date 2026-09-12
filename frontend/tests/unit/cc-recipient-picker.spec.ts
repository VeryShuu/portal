/**
 * Characterization-тесты для ``CcRecipientPicker.vue`` (блок «Ответить всем»).
 *
 * Фокус — чистая логика компонента (без рендера Naive UI ``n-select``):
 * - ``searchHelpdeskUsers`` дёргается с trimmed query;
 * - onSelect отличает пользователя справочника от external email;
 * - дедуп по email (case-insensitive);
 * - remove выбрасывает получателя.
 *
 * Naive UI мокается целиком (как meeting-form-dialog.spec.ts) — ``NSelect``
 * становится dumb-stub, чьи ``@search``/``@update:value`` эмитятся из теста
 * через ``$emit`` (Vue 3 передает хендлеры в stub как ``onSearch`` props).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import type { HelpdeskUserOption } from '../../src/api/helpdesk'

const mockSearchHelpdeskUsers = vi.fn()

vi.mock('../../src/api/helpdesk', () => ({
  searchHelpdeskUsers: mockSearchHelpdeskUsers,
}))
vi.mock('../../src/composables/useDebounceFn', () => ({
  // Мгновенный passthrough — не ждём 300ms debounce в тесте.
  useDebounceFn: (fn: (...a: any[]) => any) => fn,
}))
vi.mock('naive-ui', () => ({
  NSelect: {
    name: 'NSelect',
    template: '<select class="n-select" />',
    props: ['value', 'options', 'loading', 'placeholder', 'disabled', 'renderLabel'],
    emits: ['search', 'update:value'],
  },
}))

const i18n = createI18n({
  legacy: false,
  locale: 'ru',
  missingWarn: false,
  fallbackWarn: false,
  messages: { ru: {}, en: {} },
})

async function mountPicker(modelValue: any[] = []) {
  const CcRecipientPicker = (
    await import('../../src/components/helpdesk/CcRecipientPicker.vue')
  ).default
  return mount(CcRecipientPicker, {
    props: { modelValue },
    global: { plugins: [i18n] },
  })
}

function select(wrapper: ReturnType<typeof mount>) {
  return wrapper.findComponent({ name: 'NSelect' })
}

describe('CcRecipientPicker', () => {
  beforeEach(() => {
    mockSearchHelpdeskUsers.mockReset()
  })

  it('calls searchHelpdeskUsers with trimmed query on search', async () => {
    mockSearchHelpdeskUsers.mockResolvedValue([])
    const wrapper = await mountPicker()

    select(wrapper).vm.$emit('search', '  Иван  ')
    await flushPromises()

    expect(mockSearchHelpdeskUsers).toHaveBeenCalledWith('Иван')
  })

  it('does not search when query shorter than 3 chars', async () => {
    mockSearchHelpdeskUsers.mockResolvedValue([])
    const wrapper = await mountPicker()

    select(wrapper).vm.$emit('search', 'Ив')
    await flushPromises()

    expect(mockSearchHelpdeskUsers).not.toHaveBeenCalled()
  })

  it('selecting a directory user emits CcRecipient with source=directory', async () => {
    const user: HelpdeskUserOption = {
      user_id: 'u1',
      full_name: 'Иван Петров',
      email: 'ivan@corp.local',
    }
    mockSearchHelpdeskUsers.mockResolvedValue([user])
    const wrapper = await mountPicker()

    select(wrapper).vm.$emit('search', 'Иван')
    await flushPromises()
    select(wrapper).vm.$emit('update:value', ['u1'])
    await flushPromises()

    const emitted = wrapper.emitted('update:modelValue')
    expect(emitted).toBeTruthy()
    expect(emitted![0][0]).toEqual([
      { email: 'ivan@corp.local', name: 'Иван Петров', source: 'directory' },
    ])
  })

  it('external email (not in directory) is addable via ext: prefix', async () => {
    mockSearchHelpdeskUsers.mockResolvedValue([])
    const wrapper = await mountPicker()

    select(wrapper).vm.$emit('update:value', ['ext:test@external.com'])
    await flushPromises()

    const emitted = wrapper.emitted('update:modelValue')
    expect(emitted![0][0]).toEqual([
      { email: 'test@external.com', name: null, source: 'external' },
    ])
  })

  it('dedupes by lowercased email (directory user already in list)', async () => {
    const user: HelpdeskUserOption = {
      user_id: 'u1',
      full_name: 'Иван',
      email: 'Ivan@Corp.Local',
    }
    mockSearchHelpdeskUsers.mockResolvedValue([user])
    const wrapper = await mountPicker([
      { email: 'ivan@corp.local', name: 'уже выбран', source: 'directory' as const },
    ])

    select(wrapper).vm.$emit('search', 'Иван')
    await flushPromises()
    select(wrapper).vm.$emit('update:value', ['u1'])
    await flushPromises()

    // Дубликат по email (case-insensitive) — не добавлен, эмита нет.
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  })

  it('remove emits filtered list without the recipient', async () => {
    const wrapper = await mountPicker([
      { email: 'a@x.com', name: 'A', source: 'directory' as const },
      { email: 'b@y.com', name: null, source: 'external' as const },
    ])

    ;(wrapper.vm as any).remove('a@x.com')
    await flushPromises()

    const emitted = wrapper.emitted('update:modelValue')
    expect(emitted![0][0]).toEqual([
      { email: 'b@y.com', name: null, source: 'external' },
    ])
  })

  it('external option is not shown when email already in directory results', async () => {
    const user: HelpdeskUserOption = {
      user_id: 'u1',
      full_name: 'Ivan',
      email: 'ivan@corp.local',
    }
    mockSearchHelpdeskUsers.mockResolvedValue([user])
    const wrapper = await mountPicker()

    select(wrapper).vm.$emit('search', 'ivan@corp.local')
    await flushPromises()

    // ``dropdownOptions`` пробрасывается в NSelect как ``options`` prop.
    const options = select(wrapper).props('options') as Array<{ value: string }>
    expect(options.some((o) => String(o.value).startsWith('ext:'))).toBe(false)
    expect(options).toHaveLength(1)
  })
})
