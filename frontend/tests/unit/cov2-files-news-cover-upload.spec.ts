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
    const { default: Comp } = await import('../../src/components/NewsCoverUpload.vue')
    return mount(Comp, {
      ...mountOpts(),
      props: {
        newsId: 'n-1',
        isEdit: true,
        coverImageUrl: '/cover.jpg',
        focalPoint: 'center',
        maxSizeMb: 10,
        ...props,
      },
    })
  }

  it('renders preview and updates focal point with success and error branches', async () => {
    const wrapper = await mountComp()
    expect(wrapper.find('.cover-preview').exists()).toBe(true)

    const focalButtons = wrapper.findAll('.n-button').filter((b) => b.text().includes('news.form.focal'))
    await focalButtons[0].trigger('click')
    await flushPromises()
    expect(wrapper.emitted('update:focalPoint')?.[0]).toEqual(['top'])
    expect(newsApiMock.updateNews).toHaveBeenCalledWith('n-1', { cover_focal_point: 'top' })

    newsApiMock.updateNews.mockRejectedValueOnce(new Error('x'))
    await focalButtons[2].trigger('click')
    await flushPromises()
    expect(messageMock.error).toHaveBeenCalledWith('parsed-news-error')
  })

  it('deletes cover image success and failure branches', async () => {
    const wrapper = await mountComp()
    const deleteBtn = wrapper.findAll('.n-button').find((b) => b.text().includes('news.form.coverDelete'))
    await deleteBtn!.trigger('click')
    await flushPromises()
    expect(newsApiMock.deleteNewsCover).toHaveBeenCalledWith('n-1')
    expect(wrapper.emitted('update:coverImageUrl')?.[0]).toEqual([null])

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
