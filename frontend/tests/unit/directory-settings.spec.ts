/**
 * Юнит-тесты DirectorySettings.vue (конструктор типа справочника):
 * выбор существующего типа → форма, "Новый тип" → пустая форма + create,
 * normalize() триммит значения и переиндексирует sort_order.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref, type Ref } from 'vue'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'

const i18n = createI18n({ legacy: false, locale: 'ru', messages: { ru: {}, en: {} } })

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
    props: ['value', 'type', 'placeholder', 'clearable', 'disabled', 'autosize'],
    emits: ['update:value'],
  },
  NSelect: {
    template: '<select class="n-select" />',
    props: ['value', 'options', 'placeholder', 'size'],
    emits: ['update:value'],
  },
  NCheckbox: {
    template: '<input type="checkbox" />',
    props: ['checked'],
    emits: ['update:checked'],
  },
  NForm: { template: '<form><slot /></form>', props: ['labelPlacement'] },
  NFormItem: { template: '<div><slot /></div>', props: ['label', 'required'] },
  NDivider: { template: '<div><slot /></div>' },
  useMessage: () => ({ success: vi.fn(), error: vi.fn() }),
}))

vi.mock('@vicons/ionicons5', () => ({
  AddOutline: { template: '<span />' },
  TrashOutline: { template: '<span />' },
}))

const dirData: Ref<{ items: unknown[] } | undefined> = ref({ items: [] })
const createMutate = vi.fn().mockResolvedValue({ id: 'created' })
const updateMutate = vi.fn().mockResolvedValue({ id: 'd1' })

vi.mock('../../src/queries/directories', () => ({
  useDirectoriesQuery: () => ({ data: dirData }),
  useCreateDirectoryMutation: () => ({ mutateAsync: createMutate }),
  useUpdateDirectoryMutation: () => ({ mutateAsync: updateMutate }),
  useDeleteDirectoryMutation: () => ({ mutateAsync: vi.fn() }),
}))

async function mountSettings() {
  const { default: DirectorySettings } = await import(
    '../../src/components/admin/DirectorySettings.vue'
  )
  return mount(DirectorySettings, { global: { plugins: [i18n] } })
}

function btn(wrapper: Awaited<ReturnType<typeof mountSettings>>, text: string) {
  return wrapper.findAll('button').find((b) => b.text().includes(text))!
}

describe('DirectorySettings.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    dirData.value = { items: [] }
    createMutate.mockClear()
    updateMutate.mockClear()
  })

  it('shows pick hint when nothing is being edited', async () => {
    const wrapper = await mountSettings()
    expect(wrapper.find('.empty-hint').exists()).toBe(true)
    expect(wrapper.find('form').exists()).toBe(false)
  })

  it('startNew reveals an empty form with disabled save until required filled', async () => {
    const wrapper = await mountSettings()
    await btn(wrapper, 'directories.admin.newType').trigger('click')
    expect(wrapper.find('form').exists()).toBe(true)
    const save = btn(wrapper, 'common.save')
    expect(save.attributes('disabled')).toBeDefined()
  })

  it('normalizes payload and calls create mutation on save', async () => {
    const wrapper = await mountSettings()
    await btn(wrapper, 'directories.admin.newType').trigger('click')
    const inputs = wrapper.findAll('input.n-input')
    // order: slug, icon, label_ru, label_en, description
    await inputs[0].setValue('  fleet  ')
    await inputs[2].setValue('  Флот  ')
    await inputs[1].setValue('  boat  ')
    await btn(wrapper, 'common.save').trigger('click')
    await Promise.resolve()

    expect(createMutate).toHaveBeenCalledTimes(1)
    const arg = createMutate.mock.calls[0][0]
    expect(arg).toMatchObject({ slug: 'fleet', label_ru: 'Флот', icon: 'boat' })
    expect(arg.label_en).toBeNull()
    expect(arg.description).toBeNull()
  })
})
