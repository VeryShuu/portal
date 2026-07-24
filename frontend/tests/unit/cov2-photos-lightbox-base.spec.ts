import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, enableAutoUnmount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NButton: { template: '<button @click="$emit(\'click\')"><slot /></button>', props: ['type', 'size', 'disabled', 'loading', 'ghost', 'quaternary', 'tertiary', 'circle', 'title'], emits: ['click'] },
  NButtonGroup: { template: '<div><slot /></div>' },
  NSpin: { template: '<div class="n-spin" />', props: ['show', 'size'] },
  NEmpty: { template: '<div class="n-empty"><slot /></div>', props: ['description'] },
  NAlert: { template: '<div class="n-alert"><slot /></div>', props: ['type', 'title', 'showIcon', 'closable'] },
  NTabs: { template: '<div class="n-tabs"><slot /></div>', props: ['value', 'type', 'animated', 'size'], emits: ['update:value'] },
  NTabPane: { template: '<div class="n-tab-pane"><slot /></div>', props: ['name', 'tab'] },
  NIcon: { template: '<span class="n-icon"><slot /></span>', props: ['size', 'color', 'component'] },
  NCard: { template: '<div class="n-card"><slot /></div>', props: ['bordered', 'size', 'title'] },
  NInput: { template: '<input :value="value" @input="$emit(\'update:value\', $event.target.value)" />', props: ['value', 'placeholder', 'type', 'maxlength', 'size', 'clearable'], emits: ['update:value'] },
  NSelect: { template: '<select />', props: ['value', 'options', 'placeholder', 'multiple', 'clearable'], emits: ['update:value'] },
  NPagination: { template: '<div class="n-pagination" />', props: ['page', 'pageCount', 'pageSize'], emits: ['update:page'] },
  NRadioGroup: { template: '<div><slot /></div>', props: ['value'], emits: ['update:value'] },
  NRadioButton: { template: '<label><slot /></label>', props: ['value', 'label'] },
  NModal: { template: '<div class="n-modal" v-if="show"><slot /></div>', props: ['show', 'title', 'preset'], emits: ['update:show'] },
  NDrawer: { template: '<div class="n-drawer" v-if="show"><slot /></div>', props: ['show', 'width', 'placement'], emits: ['update:show'] },
  NDrawerContent: { template: '<div><slot /></div>', props: ['title', 'closable'] },
  NForm: { template: '<form><slot /></form>', props: ['model', 'rules'] },
  NFormItem: { template: '<div><slot /></div>', props: ['label', 'path'] },
  NCheckbox: { template: '<input type="checkbox" />', props: ['checked'], emits: ['update:checked'] },
  NSwitch: { template: '<input type="checkbox" />', props: ['value'], emits: ['update:value'] },
  NDataTable: { template: '<div class="n-data-table" />', props: ['data', 'columns', 'pagination', 'loading'] },
  NSpace: { template: '<div><slot /></div>', props: ['justify', 'align', 'size', 'vertical'] },
  NTag: { template: '<span class="n-tag"><slot /></span>', props: ['type', 'size', 'closable', 'bordered'] },
  NTooltip: { template: '<div><slot /><slot name="trigger" /></div>' },
  NPopconfirm: { template: '<div><slot /><slot name="trigger" /></div>' },
  NDivider: { template: '<hr />' },
  NText: { template: '<span><slot /></span>', props: ['depth', 'type'] },
  NDynamicTags: { template: '<div><slot /></div>', props: ['value'], emits: ['update:value'] },
  NUpload: { template: '<div><slot /></div>', props: ['multiple', 'showFileList', 'fileList', 'customRequest'] },
  NColorPicker: { template: '<input type="color" />', props: ['value'], emits: ['update:value'] },
  NInputNumber: { template: '<input type="number" />', props: ['value', 'min', 'max'], emits: ['update:value'] },
  NScrollbar: { template: '<div><slot /></div>' },
  NCollapse: { template: '<div><slot /></div>' },
  NCollapseItem: { template: '<div><slot /></div>', props: ['title', 'name'] },
  NCode: { template: '<pre><slot /></pre>', props: ['code', 'language'] },
  NDatePicker: { template: '<input type="date" />', props: ['value', 'type', 'placeholder'], emits: ['update:value'] },
  NSkeleton: { template: '<div class="n-skeleton" />', props: ['text', 'repeat'] },
  NTimePicker: { template: '<input type="time" />', props: ['value'], emits: ['update:value'] },
  NList: { template: '<ul><slot /></ul>' },
  NListItem: { template: '<li><slot /></li>' },
  NThing: { template: '<div><slot /></div>', props: ['title', 'description'] },
  NAvatar: { template: '<div class="n-avatar" />', props: ['src', 'size', 'round'] },
  NBadge: { template: '<div><slot /></div>', props: ['value', 'max'] },
  NDescriptions: { template: '<div><slot /></div>', props: ['column', 'bordered'] },
  NDescriptionsItem: { template: '<div><slot /></div>', props: ['label'] },
  useMessage: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
  useDialog: () => ({ warning: vi.fn(), error: vi.fn(), success: vi.fn() }),
  useLoadingBar: () => ({ start: vi.fn(), finish: vi.fn(), error: vi.fn() }),
}))

vi.mock('vue-router', () => ({
  useRouter: vi.fn(() => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() })),
  useRoute: vi.fn(() => ({ params: {}, query: {}, path: '/photos', name: 'photos' })),
  RouterLink: { template: '<a><slot /></a>', props: ['to'] },
}))

vi.mock('@tanstack/vue-query', () => ({
  useQuery: vi.fn(() => ({ data: { value: undefined }, isLoading: { value: false }, isFetching: { value: false }, error: { value: null }, refetch: vi.fn() })),
  useMutation: vi.fn(() => ({ mutate: vi.fn(), mutateAsync: vi.fn().mockResolvedValue(undefined), isPending: { value: false }, isError: { value: false } })),
  useQueryClient: vi.fn(() => ({ invalidateQueries: vi.fn(), removeQueries: vi.fn(), setQueryData: vi.fn() })),
  useInfiniteQuery: vi.fn(() => ({ data: { value: { pages: [] } }, isLoading: { value: false }, fetchNextPage: vi.fn(), hasNextPage: { value: false } })),
  keepPreviousData: undefined,
}))

vi.mock('@/api', () => ({ api: vi.fn().mockResolvedValue({ data: {} }), apiUpload: vi.fn().mockResolvedValue({ data: {} }), BASE_URL: '/api/v1' }))
vi.mock('@vicons/ionicons5', () => new Proxy({}, { get: () => ({ template: '<span />' }) }))
vi.mock('@vicons/fluent', () => new Proxy({}, { get: () => ({ template: '<span />' }) }))

import LightboxBase from '@/components/photos/LightboxBase.vue'

const globalPlugins = {
  plugins: [i18n],
  stubs: { RouterLink: { template: '<a><slot /></a>' } },
}

// Гарантированно размонтирует wrapper после каждого it → срабатывает
// onUnmounted → clearFocusTimer(). Без этого отложенный setTimeout(50ms)
// из watch(props.modelValue) протекает за пределы жизни компонента и падает
// в Vitest teardown с ReferenceError: document is not defined (CI блокер).
enableAutoUnmount(afterEach)

describe('cov2 LightboxBase', () => {
  beforeEach(() => {
    document.body.innerHTML = '<button id="prev-focus">prev</button>'
  })

  afterEach(() => {
    document.body.innerHTML = ''
    vi.useRealTimers()
  })

  it('does not render when closed', () => {
    const wrapper = mount(LightboxBase, {
      props: { modelValue: null, total: 3 },
      global: globalPlugins,
    })
    expect(wrapper.exists()).toBe(true)
    expect(wrapper.find('.lightbox').exists()).toBe(false)
  })

  it('renders navigation only when total > 1 and closes by button', async () => {
    const wrapper = mount(LightboxBase, {
      props: { modelValue: 0, total: 2 },
      attachTo: document.body,
      global: globalPlugins,
      slots: { default: '<div class="slot-content" />' },
    })
    expect(wrapper.find('.lightbox').exists()).toBe(true)
    expect(wrapper.find('.lightbox__nav--prev').exists()).toBe(true)
    expect(wrapper.find('.lightbox__nav--next').exists()).toBe(true)
    await wrapper.find('.lightbox__close').trigger('click')
    expect(wrapper.emitted('close')).toBeTruthy()
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([null])
  })

  it('prev/next handle wrap and non-loop branches', async () => {
    const wrapper = mount(LightboxBase, {
      props: { modelValue: 0, total: 2, loop: true },
      attachTo: document.body,
      global: globalPlugins,
    })

    await wrapper.find('.lightbox__nav--prev').trigger('click')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([1])

    await wrapper.setProps({ modelValue: 1 })
    await wrapper.find('.lightbox__nav--next').trigger('click')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([0])

    await wrapper.setProps({ modelValue: 0, loop: false })
    await wrapper.find('.lightbox__nav--prev').trigger('click')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([0])
  })

  it('handles keydown arrows/escape and emits generic keydown for other keys', async () => {
    const wrapper = mount(LightboxBase, {
      props: { modelValue: 0, total: 3 },
      attachTo: document.body,
      global: globalPlugins,
    })

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight' }))
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft' }))
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'z' }))
    await wrapper.vm.$nextTick()

    expect(wrapper.emitted('next')).toBeTruthy()
    expect(wrapper.emitted('prev')).toBeTruthy()
    expect(wrapper.emitted('close')).toBeTruthy()
    expect(wrapper.emitted('keydown')).toBeTruthy()
  })

  it('does not navigate on keydown when target is input-like element', async () => {
    const wrapper = mount(LightboxBase, {
      props: { modelValue: 1, total: 5 },
      attachTo: document.body,
      global: globalPlugins,
    })

    const input = document.createElement('input')
    document.body.appendChild(input)
    const event = new KeyboardEvent('keydown', { key: 'ArrowLeft' })
    Object.defineProperty(event, 'target', { value: input })
    window.dispatchEvent(event)
    await wrapper.vm.$nextTick()

    expect(wrapper.emitted('prev')).toBeFalsy()
    expect(wrapper.emitted('keydown')).toBeTruthy()
  })
})
