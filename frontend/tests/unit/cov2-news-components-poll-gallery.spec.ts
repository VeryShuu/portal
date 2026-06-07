import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref, defineComponent, nextTick } from 'vue'
import { createI18n } from 'vue-i18n'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

const galleryDataState = {
  data: [] as any[],
}

const uploadMutateAsync = vi.fn()
const deleteMutateAsync = vi.fn()
const reorderMutateAsync = vi.fn()
const messageError = vi.fn()

vi.mock('naive-ui', () => ({
  NButton: {
    template: '<button class="n-button" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'size', 'loading', 'disabled', 'ghost', 'circle', 'dashed', 'quaternary'],
    emits: ['click'],
  },
  NIcon: { template: '<span class="n-icon"><slot /></span>', props: ['component'] },
  NFormItem: { template: '<div class="n-form-item"><slot /></div>', props: ['label', 'required'] },
  NInput: {
    template: '<input class="n-input" :value="value" @input="$emit(\'update:value\', $event.target.value)" />',
    props: ['value', 'placeholder', 'maxlength', 'showCount'],
    emits: ['update:value'],
  },
  NCheckbox: {
    template: '<input class="n-checkbox" type="checkbox" :checked="checked" @change="$emit(\'update:checked\', $event.target.checked)" />',
    props: ['checked', 'disabled'],
    emits: ['update:checked'],
  },
  NInputNumber: {
    template: '<input class="n-input-number" type="number" :value="value" @input="$emit(\'update:value\', Number($event.target.value))" />',
    props: ['value', 'min', 'max', 'clearable', 'disabled'],
    emits: ['update:value'],
  },
  NUpload: {
    name: 'NUpload',
    template: '<div class="n-upload"><slot /></div>',
    props: ['showFileList', 'customRequest', 'disabled', 'accept', 'multiple'],
  },
  useMessage: () => ({ success: vi.fn(), error: messageError, warning: vi.fn(), info: vi.fn() }),
}))

vi.mock('vue-router', () => ({
  useRouter: vi.fn(() => ({ push: vi.fn(), replace: vi.fn() })),
  useRoute: vi.fn(() => ({ params: {}, query: {} })),
}))

vi.mock('@tanstack/vue-query', () => ({
  useQuery: vi.fn(() => ({ data: { value: undefined }, isLoading: { value: false }, isFetching: { value: false }, error: { value: null }, refetch: vi.fn() })),
  useMutation: vi.fn(() => ({ mutate: vi.fn(), mutateAsync: vi.fn().mockResolvedValue(undefined), isPending: { value: false }, isError: { value: false } })),
  useQueryClient: vi.fn(() => ({ invalidateQueries: vi.fn(), removeQueries: vi.fn(), setQueryData: vi.fn() })),
  useInfiniteQuery: vi.fn(() => ({ data: { value: { pages: [] } }, isLoading: { value: false }, fetchNextPage: vi.fn(), hasNextPage: { value: false } })),
  keepPreviousData: undefined,
}))

vi.mock('../../src/api', () => ({
  api: vi.fn().mockResolvedValue({ data: {} }),
  apiUpload: vi.fn().mockResolvedValue({ data: {} }),
  BASE_URL: '/api/v1',
}))

vi.mock('@vicons/ionicons5', () => new Proxy({}, { get: () => ({ template: '<span />' }) }))
vi.mock('@vicons/fluent', () => new Proxy({}, { get: () => ({ template: '<span />' }) }))

vi.mock('../../src/queries/news', () => ({
  useNewsGalleryQuery: vi.fn(() => ({ data: ref(galleryDataState.data), isLoading: ref(false) })),
  useUploadGalleryImageMutation: vi.fn(() => ({ mutateAsync: uploadMutateAsync })),
  useDeleteGalleryImageMutation: vi.fn(() => ({ mutateAsync: deleteMutateAsync })),
  useReorderGalleryMutation: vi.fn(() => ({ mutateAsync: reorderMutateAsync })),
}))

vi.mock('../../src/utils/parseApiError', () => ({
  parseApiError: vi.fn(() => 'parse-error'),
}))

vi.mock('../../src/components/news/poll/PollProgress.vue', () => ({
  default: defineComponent({
    name: 'PollProgress',
    props: ['percent', 'votesCount'],
    template: '<div class="poll-progress" />',
  }),
}))

describe('cov2 PollPanelVoting.vue', () => {
  const baseForm = () => ({
    questions: [
      {
        text: 'Q1',
        is_required: false,
        is_multiple: false,
        allow_custom_answer: false,
        max_choices: null,
        sort_order: 0,
        options: [
          { text: 'O1', image_url: '', sort_order: 0 },
          { text: 'O2', image_url: '', sort_order: 1 },
        ],
      },
    ],
  })

  it('mounts, emits save/cancel, and adds/removes items through controls', async () => {
    const Cmp = (await import('../../src/components/news/poll-panel/PollPanelVoting.vue')).default
    const form = baseForm()

    const w = mount(Cmp, {
      props: {
        form,
        hasVotes: false,
        uploadingImage: false,
        newsId: 'n1',
        saving: false,
        showCancelButton: true,
        onImageUpload: vi.fn(async () => undefined),
      },
      global: { plugins: [i18n] },
    })

    expect(w.exists()).toBe(true)

    const addQuestionBtn = w.findAll('button.n-button').find((b) => b.text().includes('news.poll.editor.addQuestion'))
    await addQuestionBtn!.trigger('click')
    await nextTick()
    expect(form.questions).toHaveLength(2)

    const addOptionBtn = w.findAll('button.n-button').find((b) => b.text().includes('news.poll.editor.addOption'))
    await addOptionBtn!.trigger('click')
    await nextTick()
    expect(form.questions[0].options).toHaveLength(3)

    const actionBtns = w.findAll('.poll-form__actions .n-button')
    await actionBtns[0].trigger('click')
    await actionBtns[1].trigger('click')

    expect(w.emitted('save')).toBeTruthy()
    expect(w.emitted('cancel')).toBeTruthy()
  })

  it('respects hasVotes disabled branches and resets max_choices on multiple toggle off', async () => {
    const Cmp = (await import('../../src/components/news/poll-panel/PollPanelVoting.vue')).default
    const form = {
      questions: [{
        text: 'Q1',
        is_required: false,
        is_multiple: true,
        allow_custom_answer: false,
        max_choices: 2,
        sort_order: 0,
        options: [
          { text: 'O1', image_url: '', sort_order: 0 },
          { text: 'O2', image_url: '', sort_order: 1 },
        ],
      }],
    }

    const w = mount(Cmp, {
      props: {
        form,
        hasVotes: true,
        uploadingImage: false,
        newsId: 'n1',
        saving: false,
        showCancelButton: false,
        onImageUpload: vi.fn(async () => undefined),
      },
      global: { plugins: [i18n] },
    })

    const checkbox = w.findAll('.n-checkbox')[1]
    await checkbox.setValue(false)
    await nextTick()
    expect(form.questions[0].max_choices).toBeNull()

    const addQuestionBtn = w.findAll('button.n-button').find((b) => b.text().includes('news.poll.editor.addQuestion'))
    expect(addQuestionBtn!.attributes('disabled')).toBeDefined()
  })
})

describe('cov2 NewsGalleryPanel.vue', () => {
  beforeEach(() => {
    galleryDataState.data = []
    uploadMutateAsync.mockReset()
    deleteMutateAsync.mockReset()
    reorderMutateAsync.mockReset()
    messageError.mockReset()
  })

  it('renders save-first hint when newsId is missing', async () => {
    const Cmp = (await import('../../src/components/NewsGalleryPanel.vue')).default
    const w = mount(Cmp, { props: { newsId: undefined }, global: { plugins: [i18n] } })
    expect(w.text()).toContain('news.form.saveFirst')
  })

  it('loads gallery, deletes image, and reorders by drag-drop', async () => {
    galleryDataState.data = [
      { id: 'g1', url: '/1.jpg', original_name: '1', sort_order: 0 },
      { id: 'g2', url: '/2.jpg', original_name: '2', sort_order: 1 },
    ]
    deleteMutateAsync.mockResolvedValue(undefined)
    reorderMutateAsync.mockResolvedValue(undefined)

    const Cmp = (await import('../../src/components/NewsGalleryPanel.vue')).default
    const w = mount(Cmp, { props: { newsId: 'n1' }, global: { plugins: [i18n] } })
    await flushPromises()

    expect(w.findAll('.gallery-item')).toHaveLength(2)

    let items = w.findAll('.gallery-item')
    await items[0].trigger('dragstart')
    await items[1].trigger('drop')
    await flushPromises()
    expect(reorderMutateAsync).toHaveBeenCalled()

    await w.findAll('.gallery-item .n-button')[0].trigger('click')
    await flushPromises()
    expect(deleteMutateAsync).toHaveBeenCalledWith({ newsId: 'n1', imgId: 'g2' })
  })

  it('handles upload success/error and card drop branches', async () => {
    uploadMutateAsync.mockResolvedValueOnce({ id: 'g3', url: '/3.jpg', original_name: '3', sort_order: 0 })
    uploadMutateAsync.mockRejectedValueOnce(new Error('x'))

    const Cmp = (await import('../../src/components/NewsGalleryPanel.vue')).default
    const w = mount(Cmp, { props: { newsId: 'n1' }, global: { plugins: [i18n] } })
    await flushPromises()

    const uploadComp = w.findComponent({ name: 'NUpload' })
    const customRequest = uploadComp.props('customRequest') as (o: any) => Promise<void>

    await customRequest({ file: { file: new File(['a'], 'a.png', { type: 'image/png' }) }, onFinish: vi.fn(), onError: vi.fn() })
    await customRequest({ file: { file: new File(['a'], 'a.png', { type: 'image/png' }) }, onFinish: vi.fn(), onError: vi.fn() })
    expect(messageError).toHaveBeenCalled()

    await w.trigger('dragover', { dataTransfer: { types: ['Files'] } })
    await nextTick()

    await w.trigger('drop', { dataTransfer: { files: [new File(['x'], 'x.txt', { type: 'text/plain' })] } })
    expect(uploadMutateAsync).toHaveBeenCalledTimes(2)
  })
})

describe('cov2 PollOption.vue', () => {
  const question = {
    id: 'q1',
    text: 'Question',
    is_required: false,
    is_multiple: false,
    max_choices: null,
    sort_order: 0,
    options: [],
  }

  it('renders text mode and emits opt-click/opt-change', async () => {
    const Cmp = (await import('../../src/components/news/poll/PollOption.vue')).default
    const w = mount(Cmp, {
      props: {
        opt: { id: 'o1', text: 'Option 1', image_url: null, votes_percent: 33.3, votes_count: 3, sort_order: 0 },
        question,
        hasImages: false,
        selected: true,
        hasVoted: false,
        submitting: false,
        canVote: true,
        isAuthenticated: true,
        canSeeResults: true,
      },
      global: { plugins: [i18n] },
    })

    expect(w.find('.poll-progress').exists()).toBe(true)
    await w.find('.news-poll__option').trigger('click')
    await w.find('input.news-poll__input').trigger('change')
    expect(w.emitted('opt-click')![0]).toEqual(['o1'])
    expect(w.emitted('opt-change')![0]).toEqual(['o1'])
  })

  it('renders image grid mode without input when cannot vote', async () => {
    const Cmp = (await import('../../src/components/news/poll/PollOption.vue')).default
    const w = mount(Cmp, {
      props: {
        opt: { id: 'o2', text: 'Option 2', image_url: '/x.png', votes_percent: null, votes_count: 0, sort_order: 0 },
        question: { ...question, is_multiple: true },
        hasImages: true,
        selected: false,
        hasVoted: true,
        submitting: false,
        canVote: false,
        isAuthenticated: true,
        canSeeResults: false,
      },
      global: { plugins: [i18n] },
    })

    expect(w.find('.news-poll__option-img').exists()).toBe(true)
    expect(w.find('input.news-poll__input').exists()).toBe(false)
  })
})
