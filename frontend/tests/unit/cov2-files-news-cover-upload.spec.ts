import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

const messageMock = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }))

const newsApiMock = vi.hoisted(() => ({
  uploadNewsCover: vi.fn(async () => ({ cover_image_url: '/new-cover.jpg' })),
  deleteNewsCover: vi.fn(async () => ({})),
  updateNews: vi.fn(async () => ({})),
}))

const parseApiErrorMock = vi.hoisted(() => ({ parseApiError: vi.fn(() => 'parsed-news-error') }))

vi.mock('naive-ui', () => ({
  NButton: { template: '<button class="n-button" :disabled="disabled" @click="$emit(\'click\', $event)"><slot /><slot name="icon" /></button>', props: ['size', 'type', 'secondary', 'loading', 'ghost', 'disabled'], emits: ['click'] },
  NButtonGroup: { template: '<div class="n-button-group"><slot /></div>', props: ['size'] },
  NIcon: { template: '<span class="n-icon"><slot /></span>', props: ['size', 'class'] },
  NSlider: { name: 'NSlider', template: '<div class="n-slider" />', props: ['value', 'min', 'max', 'step', 'formatTooltip'], emits: ['update:value'] },
  NUpload: { name: 'NUpload', template: '<div class="n-upload"><slot /></div>', props: ['accept', 'showFileList', 'customRequest', 'disabled'] },
  useMessage: () => messageMock,
}))

vi.mock('../../src/api/news', () => newsApiMock)
vi.mock('../../src/utils/parseApiError', () => parseApiErrorMock)
vi.mock('@vicons/ionicons5', () => ({
  ImageOutline: { template: '<span />' },
  TrashOutline: { template: '<span />' },
}))

function mountOpts() {
  return { global: { plugins: [i18n] } }
}

describe('NewsCoverUpload', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  async function mountComp(props: Record<string, unknown> = {}) {
    const { default: Comp } = await import('../../src/components/news/NewsCoverUpload.vue')
    return mount(Comp, {
      ...mountOpts(),
      props: {
        newsId: 'n-1',
        isEdit: true,
        coverImageUrl: '/cover.jpg',
        focalX: null,
        focalY: null,
        focalZoom: null,
        maxSizeMb: 10,
        ...props,
      },
    })
  }

  function stubRect(wrapper: Awaited<ReturnType<typeof mountComp>>) {
    const el = wrapper.find('.cover-preview').element as HTMLElement
    el.getBoundingClientRect = () => ({
      left: 0, top: 0, width: 200, height: 100, right: 200, bottom: 100,
      x: 0, y: 0, toJSON() {},
    }) as DOMRect
  }

  it('renders preview and updates focal point via drag, persisting on release', async () => {
    vi.useFakeTimers()
    const wrapper = await mountComp()
    expect(wrapper.find('.cover-preview').exists()).toBe(true)
    stubRect(wrapper)

    const preview = wrapper.find('.cover-preview')
    await preview.trigger('pointerdown', { clientX: 100, clientY: 50, pointerId: 1 })
    expect(wrapper.emitted('update:focalX')?.pop()).toEqual([50])
    expect(wrapper.emitted('update:focalY')?.pop()).toEqual([50])

    await preview.trigger('pointermove', { clientX: 200, clientY: 100, pointerId: 1 })
    expect(wrapper.emitted('update:focalX')?.pop()).toEqual([100])
    expect(wrapper.emitted('update:focalY')?.pop()).toEqual([100])

    await preview.trigger('pointerup', { pointerId: 1 })
    await vi.runAllTimersAsync()
    expect(newsApiMock.updateNews).toHaveBeenCalledWith('n-1', { cover_focal_x: 100, cover_focal_y: 100, cover_focal_zoom: null })
    vi.useRealTimers()
  })

  it('zooms in via wheel and persists, clearing zoom back to null at 100%', async () => {
    vi.useFakeTimers()
    const wrapper = await mountComp({ focalZoom: 100 })
    const preview = wrapper.find('.cover-preview')

    await preview.trigger('wheel', { deltaY: -100 })
    expect(wrapper.emitted('update:focalZoom')?.pop()).toEqual([110])

    await preview.trigger('wheel', { deltaY: 100 })
    expect(wrapper.emitted('update:focalZoom')?.pop()).toEqual([null])

    await vi.runAllTimersAsync()
    expect(newsApiMock.updateNews).toHaveBeenCalled()
    vi.useRealTimers()
  })

  it('clamps out-of-bounds drag and surfaces persist errors', async () => {
    vi.useFakeTimers()
    const wrapper = await mountComp()
    stubRect(wrapper)

    const preview = wrapper.find('.cover-preview')
    await preview.trigger('pointerdown', { clientX: -50, clientY: 999, pointerId: 1 })
    expect(wrapper.emitted('update:focalX')?.pop()).toEqual([0])
    expect(wrapper.emitted('update:focalY')?.pop()).toEqual([100])

    newsApiMock.updateNews.mockRejectedValueOnce(new Error('x'))
    await preview.trigger('pointerup', { pointerId: 1 })
    await vi.runAllTimersAsync()
    expect(messageMock.error).toHaveBeenCalledWith('parsed-news-error')
    vi.useRealTimers()
  })

  it('nudges focal point with arrow keys', async () => {
    vi.useFakeTimers()
    const wrapper = await mountComp()
    const preview = wrapper.find('.cover-preview')

    await preview.trigger('keydown', { key: 'ArrowRight' })
    expect(wrapper.emitted('update:focalX')?.pop()).toEqual([51])
    await preview.trigger('keydown', { key: 'ArrowDown', shiftKey: true })
    expect(wrapper.emitted('update:focalY')?.pop()).toEqual([60])

    await vi.runAllTimersAsync()
    expect(newsApiMock.updateNews).toHaveBeenCalled()
    vi.useRealTimers()
  })

  it('deletes cover image success and failure branches', async () => {
    const wrapper = await mountComp()
    const deleteBtn = wrapper.findAll('.n-button').find((b) => b.text().includes('news.form.coverDelete'))
    await deleteBtn!.trigger('click')
    await flushPromises()
    expect(newsApiMock.deleteNewsCover).toHaveBeenCalledWith('n-1')
    expect(wrapper.emitted('update:coverImageUrl')?.[0]).toEqual([null])
  })

  it('surfaces delete cover errors', async () => {
    const wrapper = await mountComp()
    const deleteBtn = wrapper.findAll('.n-button').find((b) => b.text().includes('news.form.coverDelete'))
    newsApiMock.deleteNewsCover.mockRejectedValueOnce(new Error('del'))
    await deleteBtn!.trigger('click')
    await flushPromises()
    expect(messageMock.error).toHaveBeenCalledWith('parsed-news-error')
  })

  it('shows disabled dropzone when no id and no cover', async () => {
    const wrapper = await mountComp({ coverImageUrl: null, newsId: undefined })
    expect(wrapper.find('.cover-drop--disabled').exists()).toBe(true)
  })

  it('custom upload handler covers guard/success/error branches', async () => {
    const wrapper = await mountComp({ coverImageUrl: null, isEdit: true, newsId: 'n-9' })
    const upload = wrapper.findComponent({ name: 'NUpload' })
    const customRequest = upload.props('customRequest') as (...args: any[]) => any

    const onFinish = vi.fn()
    const onError = vi.fn()

    await customRequest({ file: { file: undefined }, onFinish, onError })
    expect(onError).toHaveBeenCalled()

    const goodFile = new File(['img'], 'img.png', { type: 'image/png' })
    await customRequest({ file: { file: goodFile }, onFinish, onError })
    await flushPromises()
    expect(newsApiMock.uploadNewsCover).toHaveBeenCalledWith('n-9', goodFile)
    expect(wrapper.emitted('update:coverImageUrl')?.some((x) => x[0] === '/new-cover.jpg')).toBe(true)
    expect(onFinish).toHaveBeenCalled()

    newsApiMock.uploadNewsCover.mockRejectedValueOnce(new Error('upload fail'))
    await customRequest({ file: { file: goodFile }, onFinish, onError })
    await flushPromises()
    expect(messageMock.error).toHaveBeenCalledWith('parsed-news-error')
    expect(onError).toHaveBeenCalled()
  })

  it('upload guard warns when not editable or missing newsId', async () => {
    const wrapper = await mountComp({ coverImageUrl: null, isEdit: false, newsId: 'n-1' })
    const upload = wrapper.findComponent({ name: 'NUpload' })
    const customRequest = upload.props('customRequest') as (...args: any[]) => any

    const onError = vi.fn()
    await customRequest({ file: { file: new File(['x'], 'x.png') }, onFinish: vi.fn(), onError })
    expect(messageMock.warning).toHaveBeenCalledWith('news.form.coverSaveFirst')
    expect(onError).toHaveBeenCalled()
  })
})
