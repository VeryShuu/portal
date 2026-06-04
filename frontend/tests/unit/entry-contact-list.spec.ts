/**
 * Юнит-тесты EntryContactList.vue: группировка контактов по роли, выбор
 * подписи канала (ru/en) и копирование значения в буфер обмена.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

const i18n = createI18n({
  legacy: false,
  locale: 'ru',
  messages: { ru: { directories: { copy: 'copy', copied: 'ok', copyFailed: 'fail' } }, en: {} },
})

const successSpy = vi.fn()
const errorSpy = vi.fn()

vi.mock('naive-ui', () => ({
  NIcon: { template: '<span class="n-icon"><slot /></span>', props: ['size'] },
  useMessage: () => ({ success: successSpy, error: errorSpy }),
}))

vi.mock('@vicons/ionicons5', () => ({
  CopyOutline: { template: '<span />' },
}))

const channels = [
  { key: 'email', label_ru: 'Почта', label_en: 'E-mail', sort_order: 0 },
  { key: 'iridium', label_ru: 'Иридиум', label_en: null, sort_order: 1 },
]

const contacts = [
  { id: 'c2', role: 'Капитан', channel: 'email', label: null, value: 'cap@x.ru', sort_order: 2 },
  { id: 'c1', role: 'Мостик', channel: 'email', label: 'осн', value: 'bridge@x.ru', sort_order: 0 },
  { id: 'c3', role: 'Мостик', channel: 'iridium', label: null, value: '+1', sort_order: 1 },
]

async function mountList(lang: 'ru' | 'en' = 'ru') {
  const { default: EntryContactList } = await import(
    '../../src/components/directories/EntryContactList.vue'
  )
  return mount(EntryContactList, {
    props: { contacts, channels, lang },
    global: { plugins: [i18n] },
  })
}

describe('EntryContactList.vue', () => {
  beforeEach(() => {
    successSpy.mockReset()
    errorSpy.mockReset()
  })

  it('groups contacts by role and orders by sort_order', async () => {
    const wrapper = await mountList()
    const groups = wrapper.findAll('.contact-group')
    expect(groups).toHaveLength(2)
    expect(groups[0].find('.contact-group__role').text()).toBe('Мостик')
    expect(groups[1].find('.contact-group__role').text()).toBe('Капитан')
    const firstRowValue = groups[0].findAll('.contact-row__value')[0].text()
    expect(firstRowValue).toBe('bridge@x.ru')
  })

  it('renders ru channel labels and falls back when en label is empty', async () => {
    const wrapper = await mountList('en')
    const channelLabels = wrapper.findAll('.contact-row__channel').map((n) => n.text())
    expect(channelLabels).toContain('E-mail')
    expect(channelLabels).toContain('Иридиум')
  })

  it('copies value to clipboard and shows success', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { clipboard: { writeText } })
    const wrapper = await mountList()
    await wrapper.find('.copy-btn').trigger('click')
    await Promise.resolve()
    expect(writeText).toHaveBeenCalledWith('bridge@x.ru')
    expect(successSpy).toHaveBeenCalled()
  })

  it('shows error when clipboard write fails', async () => {
    const writeText = vi.fn().mockRejectedValue(new Error('denied'))
    Object.assign(navigator, { clipboard: { writeText } })
    const wrapper = await mountList()
    await wrapper.find('.copy-btn').trigger('click')
    await Promise.resolve()
    await Promise.resolve()
    expect(errorSpy).toHaveBeenCalled()
  })
})
