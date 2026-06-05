/**
 * Юнит-тесты EntryEditDrawer.vue: формирование payload при сохранении
 * (тримминг значений, отбрасывание пустых атрибутов и контактов) и выбор
 * create- против update-мутации.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NButton: {
    template:
      '<button class="n-button" :disabled="disabled" @click="$emit(\'click\', $event)"><slot /></button>',
    props: ['type', 'quaternary', 'loading', 'size', 'dashed', 'block', 'circle', 'disabled'],
    emits: ['click'],
  },
  NIcon: { template: '<span><slot /></span>' },
  NInput: {
    template:
      '<input class="n-input" :value="value" @input="$emit(\'update:value\', $event.target.value)" />',
    props: ['value', 'type', 'placeholder', 'clearable', 'autosize'],
    emits: ['update:value'],
  },
  NSelect: { template: '<select />', props: ['value', 'options', 'size', 'placeholder'] },
  NTreeSelect: {
    template: '<div class="n-tree-select" />',
    props: ['value', 'options', 'placeholder', 'loading', 'clearable', 'filterable'],
    emits: ['update:value'],
  },
  NForm: { template: '<form><slot /></form>', props: ['labelPlacement'] },
  NFormItem: { template: '<div><slot /></div>', props: ['label', 'required', 'showLabel'] },
  NDivider: { template: '<div><slot /></div>' },
  NDrawer: { template: '<div><slot /></div>', props: ['show', 'width', 'placement'] },
  NDrawerContent: {
    template: '<div><slot /><slot name="footer" /></div>',
    props: ['title', 'closable'],
  },
  useMessage: () => ({ success: vi.fn(), error: vi.fn() }),
}))

vi.mock('@vicons/ionicons5', () => ({
  AddOutline: { template: '<span />' },
  TrashOutline: { template: '<span />' },
  ChevronUpOutline: { template: '<span />' },
  ChevronDownOutline: { template: '<span />' },
}))

const createMutate = vi.fn().mockResolvedValue({ id: 'new' })
const updateMutate = vi.fn().mockResolvedValue({ id: 'e1' })
const deleteMutate = vi.fn().mockResolvedValue(undefined)

vi.mock('../../src/queries/directories', () => ({
  useCreateEntryMutation: () => ({ mutateAsync: createMutate }),
  useUpdateEntryMutation: () => ({ mutateAsync: updateMutate }),
  useDeleteEntryMutation: () => ({ mutateAsync: deleteMutate }),
}))

vi.mock('../../src/queries/files', () => ({
  useFolderTreeQuery: () => ({
    data: { value: { items: [{ id: 'fold-1', parent_id: null, name: 'Root', nc_path: '/', permission: 'editor', inherit_permissions: false, children: [] }] } },
    isLoading: { value: false },
  }),
}))

const directory = {
  id: 'd1',
  slug: 'fleet',
  label_ru: 'Флот',
  label_en: 'Fleet',
  icon: null,
  description: null,
  field_schema: [
    { key: 'imo', label_ru: 'IMO', label_en: 'IMO', type: 'text', required: true, sort_order: 0 },
    { key: 'mmsi', label_ru: 'MMSI', label_en: 'MMSI', type: 'text', required: false, sort_order: 1 },
  ],
  channels: [{ key: 'email', label_ru: 'E-mail', label_en: 'E-mail', sort_order: 0 }],
  enabled: true,
  sort_order: 0,
  created_at: '',
  updated_at: '',
}

async function mountDrawer(entry: unknown) {
  const { default: EntryEditDrawer } = await import('../../src/components/admin/EntryEditDrawer.vue')
  return mount(EntryEditDrawer, {
    props: { show: true, directory, entry },
    global: { plugins: [i18n] },
  })
}

function saveButton(wrapper: Awaited<ReturnType<typeof mountDrawer>>) {
  return wrapper.findAll('button').find((b) => b.text() === 'common.save')!
}

describe('EntryEditDrawer.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    createMutate.mockClear()
    updateMutate.mockClear()
  })

  it('builds trimmed payload, dropping empty attrs/contacts, on update', async () => {
    const entry = {
      id: 'e1',
      directory_id: 'd1',
      name: '  Ship  ',
      folder_id: 'fold-1',
      folder_name: 'Root',
      attributes: { imo: '  123  ', mmsi: '' },
      note: '',
      sort_order: 0,
      created_by: null,
      created_at: '',
      updated_at: '',
      contacts: [
        { id: 'k1', role: '  Cap  ', channel: 'email', label: '  l  ', value: '  a@b  ', sort_order: 0 },
        { id: 'k2', role: '', channel: 'email', label: '', value: '   ', sort_order: 1 },
      ],
    }
    const wrapper = await mountDrawer(entry)
    await saveButton(wrapper).trigger('click')
    await Promise.resolve()

    expect(updateMutate).toHaveBeenCalledTimes(1)
    const { id, dto } = updateMutate.mock.calls[0][0]
    expect(id).toBe('e1')
    expect(dto).toMatchObject({
      name: 'Ship',
      folder_id: 'fold-1',
      note: null,
      attributes: { imo: '123' },
    })
    expect(dto.attributes.mmsi).toBeUndefined()
    expect(dto.contacts).toEqual([
      { role: 'Cap', channel: 'email', label: 'l', value: 'a@b', sort_order: 0 },
    ])
  })

  it('reorders contacts and assigns sort_order by new position on save', async () => {
    const entry = {
      id: 'e1',
      directory_id: 'd1',
      name: 'Ship',
      folder_id: null,
      folder_name: null,
      attributes: {},
      note: '',
      sort_order: 0,
      created_by: null,
      created_at: '',
      updated_at: '',
      contacts: [
        { id: 'k1', role: '', channel: 'email', label: '', value: 'first@b', sort_order: 0 },
        { id: 'k2', role: '', channel: 'email', label: '', value: 'second@b', sort_order: 1 },
      ],
    }
    const wrapper = await mountDrawer(entry)

    const moveUpSecond = wrapper.findAll('.contact-edit__actions')[1].findAll('button')[0]
    await moveUpSecond.trigger('click')

    await saveButton(wrapper).trigger('click')
    await Promise.resolve()

    expect(updateMutate).toHaveBeenCalledTimes(1)
    const { dto } = updateMutate.mock.calls[0][0]
    expect(dto.contacts).toEqual([
      { role: null, channel: 'email', label: null, value: 'second@b', sort_order: 0 },
      { role: null, channel: 'email', label: null, value: 'first@b', sort_order: 1 },
    ])
  })

  it('uses create mutation when no entry provided', async () => {
    const wrapper = await mountDrawer(null)
    await wrapper.find('input.n-input').setValue('New Ship')
    await saveButton(wrapper).trigger('click')
    await Promise.resolve()
    expect(createMutate).toHaveBeenCalledTimes(1)
    expect(createMutate.mock.calls[0][0]).toMatchObject({ name: 'New Ship' })
  })
})
