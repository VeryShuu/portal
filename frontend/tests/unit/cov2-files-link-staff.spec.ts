import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

const messageMock = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }))

const linksApiMock = vi.hoisted(() => ({
  createLink: vi.fn(async (dto: any) => ({ id: 'new-id', icon_url: null, created_at: '', updated_at: '', ...dto })),
  updateLink: vi.fn(async (_id: string, dto: any) => ({ id: 'edit-id', icon_url: null, created_at: '', updated_at: '', ...dto })),
  uploadLinkIcon: vi.fn(async (id: string) => ({ id, title: 'x', url: 'https://a.test', icon_url: '/icon.png', description: null, category: null, sort_order: 0, supports_sso: false, is_active: true, created_at: '', updated_at: '' })),
  deleteLinkIcon: vi.fn(async () => ({})),
}))

const storeMock = vi.hoisted(() => ({
  addLink: vi.fn(),
  updateLinkItem: vi.fn(),
  clearLinkIcon: vi.fn(),
}))

const iconState = vi.hoisted(() => ({
  iconFile: { value: null as File | null },
  iconPreview: { value: null as string | null },
  iconRemoved: { value: false },
  onIconFileChange: vi.fn(),
  removeIcon: vi.fn(() => { iconState.iconRemoved.value = true; iconState.iconFile.value = null }),
  resetIconState: vi.fn(() => { iconState.iconFile.value = null; iconState.iconPreview.value = null; iconState.iconRemoved.value = false }),
}))

vi.mock('naive-ui', () => ({
  NModal: { template: '<div class="n-modal" v-if="show"><slot /><slot name="footer" /></div>', props: ['show', 'title', 'preset', 'maskClosable'], emits: ['update:show'] },
  NForm: { template: '<form class="n-form"><slot /></form>', props: ['model', 'rules', 'labelPlacement'], methods: { validate: () => Promise.resolve() } },
  NFormItem: { template: '<div class="n-form-item"><slot /></div>', props: ['label', 'path'] },
  NInput: { template: '<input class="n-input" :value="value" @input="$emit(\'update:value\', $event.target.value)" />', props: ['value', 'placeholder', 'type', 'rows', 'clearable'], emits: ['update:value'] },
  NInputNumber: { template: '<input class="n-input-number" type="number" :value="value ?? 0" @input="$emit(\'update:value\', Number($event.target.value))" />', props: ['value', 'min'], emits: ['update:value'] },
  NCheckbox: { template: '<label class="n-checkbox"><input type="checkbox" :checked="checked" @change="$emit(\'update:checked\', $event.target.checked)" /><slot /></label>', props: ['checked'], emits: ['update:checked'] },
  NUpload: { template: '<div class="n-upload"><slot /></div>', props: ['accept', 'max', 'showFileList'], emits: ['change'] },
  NButton: { template: '<button class="n-button" :disabled="disabled" @click="$emit(\'click\', $event)"><slot /></button>', props: ['type', 'loading', 'size', 'circle', 'quaternary', 'disabled'], emits: ['click'] },
  NButtonGroup: { template: '<div class="n-button-group"><slot /></div>' },
  NIcon: { template: '<span class="n-icon"><slot /></span>' },
  NSelect: { template: '<select class="n-select" :value="value" @change="$emit(\'update:value\', $event.target.value)"><option v-for="o in options" :key="o.value" :value="o.value">{{ o.label }}</option></select>', props: ['value', 'options', 'placeholder', 'clearable', 'disabled'], emits: ['update:value'] },
  NTag: { template: '<span class="n-tag"><slot /><button class="n-tag-close" @click="$emit(\'close\')">x</button></span>', props: ['closable', 'size', 'bordered', 'type'], emits: ['close'] },
  NTooltip: { template: '<div class="n-tooltip"><slot name="trigger" /><slot /></div>', props: ['trigger'] },
  useMessage: () => messageMock,
}))

vi.mock('../../src/composables/useLinkIconUpload', () => ({ useLinkIconUpload: () => iconState }))
vi.mock('../../src/stores/links', () => ({ useLinksStore: () => storeMock }))
vi.mock('../../src/api/links', () => linksApiMock)
vi.mock('../../src/utils/url', () => ({ isSafeHttpUrl: vi.fn(() => true) }))
vi.mock('@vicons/ionicons5', () => ({
  CreateOutline: { template: '<span />' },
  DownloadOutline: { template: '<span />' },
  GridOutline: { template: '<span />' },
  ListOutline: { template: '<span />' },
  PrintOutline: { template: '<span />' },
  SearchOutline: { template: '<span />' },
}))

function mountOpts() {
  return { global: { plugins: [i18n] } }
}

function makeEditingLink(overrides: Record<string, unknown> = {}) {
  return {
    id: 'l-1',
    title: 'Title',
    url: 'https://portal.test',
    icon_url: '/old.png',
    description: 'desc',
    category: 'cat',
    sort_order: 2,
    supports_sso: true,
    is_active: true,
    created_at: '',
    updated_at: '',
    ...overrides,
  }
}

describe('LinkFormModal', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    iconState.resetIconState()
  })

  async function mountComp(props: Record<string, unknown> = {}) {
    const { default: Comp } = await import('../../src/components/links/LinkFormModal.vue')
    return mount(Comp, {
      ...mountOpts(),
      props: {
        show: true,
        editingLink: null,
        ...props,
      },
    })
  }

  it('creates link when not editing', async () => {
    const wrapper = await mountComp()
    const inputs = wrapper.findAll('.n-input')
    await inputs[0].setValue('New link')
    await inputs[1].setValue('https://new.test')

    const saveBtn = wrapper.findAll('.n-button').find((b) => b.text().includes('common.save'))
    await saveBtn!.trigger('click')
    await flushPromises()

    expect(linksApiMock.createLink).toHaveBeenCalled()
    expect(storeMock.addLink).toHaveBeenCalled()
    expect(wrapper.emitted('saved')).toBeTruthy()
    expect(wrapper.emitted('update:show')?.[0]).toEqual([false])
  })

  it('updates existing link and uploads icon when icon file is present', async () => {
    iconState.iconFile.value = new File(['x'], 'icon.png', { type: 'image/png' })
    const wrapper = await mountComp({ editingLink: makeEditingLink() })

    const saveBtn = wrapper.findAll('.n-button').find((b) => b.text().includes('common.save'))
    await saveBtn!.trigger('click')
    await flushPromises()

    expect(linksApiMock.updateLink).toHaveBeenCalledWith('l-1', expect.any(Object))
    expect(linksApiMock.uploadLinkIcon).toHaveBeenCalledWith('edit-id', expect.any(File))
    expect(storeMock.updateLinkItem).toHaveBeenCalled()
  })

  it('deletes icon when removed for editing item with existing icon', async () => {
    iconState.iconRemoved.value = true
    const wrapper = await mountComp({ editingLink: makeEditingLink({ icon_url: '/has.png' }) })

    const saveBtn = wrapper.findAll('.n-button').find((b) => b.text().includes('common.save'))
    await saveBtn!.trigger('click')
    await flushPromises()

    expect(linksApiMock.deleteLinkIcon).toHaveBeenCalledWith('edit-id')
    expect(storeMock.clearLinkIcon).toHaveBeenCalledWith('edit-id')
  })

  it('shows error message on submit failure', async () => {
    linksApiMock.createLink.mockRejectedValueOnce(new Error('fail'))
    const wrapper = await mountComp()
    const saveBtn = wrapper.findAll('.n-button').find((b) => b.text().includes('common.save'))
    await saveBtn!.trigger('click')
    await flushPromises()
    expect(messageMock.error).toHaveBeenCalledWith('errors.generic')
  })
})

describe('StaffFilters', () => {
  async function mountComp(props: Record<string, unknown> = {}) {
    const { default: Comp } = await import('../../src/components/staff/StaffFilters.vue')
    return mount(Comp, {
      ...mountOpts(),
      props: {
        searchInput: '',
        departmentFilter: null,
        officeFilter: null,
        departmentOptions: [{ label: 'IT', value: 'IT' }],
        officeOptions: [{ label: 'HQ', value: 'HQ' }],
        hasActiveFilters: false,
        view: 'table',
        effectiveView: 'table',
        isMobile: false,
        isAdmin: true,
        editMode: false,
        dirty: false,
        saving: false,
        ...props,
      },
    })
  }

  it('emits filter changes and action buttons in normal mode', async () => {
    const wrapper = await mountComp({ hasActiveFilters: true, searchInput: 'anna', departmentFilter: 'IT', officeFilter: 'HQ' })

    const input = wrapper.find('.n-input')
    await input.setValue('john')
    const selects = wrapper.findAll('.n-select')
    await selects[0].setValue('IT')
    await selects[1].setValue('HQ')

    expect(wrapper.emitted('change-search')?.[0]).toEqual(['john'])
    expect(wrapper.emitted('change-department')?.[0]).toEqual(['IT'])
    expect(wrapper.emitted('change-office')?.[0]).toEqual(['HQ'])

    const buttons = wrapper.findAll('.n-button')
    await buttons.find((b) => b.text().includes('staff.resetFilters'))!.trigger('click')
    await buttons.find((b) => b.text().includes('staff.edit.enter'))!.trigger('click')
    await buttons.find((b) => b.text().includes('staff.export'))!.trigger('click')
    await buttons.find((b) => b.text().includes('staff.print'))!.trigger('click')

    expect(wrapper.emitted('reset')).toBeTruthy()
    expect(wrapper.emitted('enter-edit')).toBeTruthy()
    expect(wrapper.emitted('export')).toBeTruthy()
    expect(wrapper.emitted('print')).toBeTruthy()

    const closers = wrapper.findAll('.n-tag-close')
    await closers[0].trigger('click')
    await closers[1].trigger('click')
    await closers[2].trigger('click')
    expect(wrapper.emitted('change-search')?.some((x) => x[0] === '')).toBe(true)
    expect(wrapper.emitted('change-department')?.some((x) => x[0] === null)).toBe(true)
    expect(wrapper.emitted('change-office')?.some((x) => x[0] === null)).toBe(true)
  })

  it('shows edit mode actions and emits save/cancel', async () => {
    const wrapper = await mountComp({ editMode: true, dirty: true, saving: true })
    expect(wrapper.text()).toContain('staff.edit.unsaved')

    const buttons = wrapper.findAll('.n-button')
    await buttons.find((b) => b.text().includes('staff.edit.discard'))!.trigger('click')
    await buttons.find((b) => b.text().includes('staff.edit.save'))!.trigger('click')

    expect(wrapper.emitted('cancel-edit')).toBeTruthy()
    expect(wrapper.emitted('save-edit')).toBeTruthy()
  })
})
