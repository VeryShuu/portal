/**
 * Юнит-тесты EntryCard.vue: рендер полей идентификации по field_schema,
 * ссылка на привязанную папку /files, кнопка/событие редактирования.
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

const i18n = createI18n({
  legacy: false,
  locale: 'ru',
  messages: { ru: { directories: { openFolder: 'folder', filesLink: 'Файлы' }, common: { edit: 'edit' } }, en: {} },
})

vi.mock('naive-ui', () => ({
  NButton: {
    template: '<button class="n-button" @click="$emit(\'click\', $event)"><slot /></button>',
    props: ['quaternary', 'circle', 'size', 'title'],
    emits: ['click'],
  },
  NIcon: { template: '<span class="n-icon"><slot /></span>', props: ['size'] },
}))

vi.mock('@vicons/ionicons5', () => ({
  CreateOutline: { template: '<span />' },
  DocumentsOutline: { template: '<span />' },
  CopyOutline: { template: '<span />' },
}))

const directory = {
  id: 'd1',
  slug: 'fleet',
  label_ru: 'Флот',
  label_en: 'Fleet',
  icon: null,
  description: null,
  field_schema: [
    { key: 'mmsi', label_ru: 'MMSI', label_en: 'MMSI', type: 'text', required: false, sort_order: 1 },
    { key: 'imo', label_ru: 'ИМО', label_en: 'IMO', type: 'text', required: true, sort_order: 0 },
  ],
  channels: [],
  enabled: true,
  sort_order: 0,
  created_at: '',
  updated_at: '',
}

const entry = {
  id: 'e1',
  directory_id: 'd1',
  name: 'Академик Казанин',
  folder_id: 'fold-1',
  folder_name: 'Академик Казанин',
  attributes: { imo: '9489481', mmsi: '' },
  note: null,
  sort_order: 0,
  created_by: null,
  created_at: '',
  updated_at: '',
  contacts: [],
}

const RouterLinkStub = {
  template: '<a class="router-link"><slot /></a>',
  props: ['to'],
}

async function mountCard(props: Record<string, unknown> = {}) {
  const { default: EntryCard } = await import('../../src/components/directories/EntryCard.vue')
  return mount(EntryCard, {
    props: { entry, directory, ...props },
    global: {
      plugins: [i18n],
      stubs: { EntryContactList: true, RouterLink: RouterLinkStub },
    },
  })
}

describe('EntryCard.vue', () => {
  it('renders only filled fields, sorted by sort_order', async () => {
    const wrapper = await mountCard()
    const labels = wrapper.findAll('.entry-card__field-label').map((n) => n.text())
    expect(labels).toEqual(['ИМО'])
    expect(wrapper.find('.entry-card__field-value').text()).toBe('9489481')
  })

  it('links bound folder to /files with folder query and shows files label', async () => {
    const wrapper = await mountCard()
    const link = wrapper.findComponent(RouterLinkStub)
    expect(link.exists()).toBe(true)
    expect(link.props('to')).toEqual({ path: '/files', query: { folder: 'fold-1' } })
    expect(link.text()).toContain('Файлы')
  })

  it('hides folder link when no folder bound', async () => {
    const wrapper = await mountCard({ entry: { ...entry, folder_id: null, folder_name: null } })
    expect(wrapper.findComponent(RouterLinkStub).exists()).toBe(false)
  })

  it('renders numeric values as code and text/email plainly', async () => {
    const wrapper = await mountCard()
    expect(wrapper.find('.entry-card__field-value').classes()).toContain('is-code')
  })

  it('emits edit when edit button clicked and canEdit', async () => {
    const wrapper = await mountCard({ canEdit: true })
    await wrapper.find('.entry-card__edit').trigger('click')
    expect(wrapper.emitted('edit')?.[0]?.[0]).toMatchObject({ id: 'e1' })
  })

  it('hides edit button when canEdit is false', async () => {
    const wrapper = await mountCard({ canEdit: false })
    expect(wrapper.find('.entry-card__edit').exists()).toBe(false)
  })
})
