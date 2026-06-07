import { describe, it, expect, vi, beforeEach } from 'vitest'
import { defineComponent, h, ref } from 'vue'
import { mount } from '@vue/test-utils'

const msg = { success: vi.fn(), error: vi.fn() }
const confirm = vi.fn()
const uploadNewsInlineMedia = vi.fn()
const parseApiError = vi.fn(() => 'parsed-upload-error')

const pollData = ref<any>(null)
const createMutateAsync = vi.fn()
const updateMutateAsync = vi.fn()
const deleteMutateAsync = vi.fn()

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string, p?: any) => (p ? `${k}:${JSON.stringify(p)}` : k) }),
}))

vi.mock('naive-ui', () => ({
  useMessage: () => msg,
}))

vi.mock('../../src/composables/useConfirmDialog', () => ({
  useConfirmDialog: () => ({ confirm }),
}))

vi.mock('../../src/api/news', () => ({
  uploadNewsInlineMedia: (...args: any[]) => uploadNewsInlineMedia(...args),
}))

vi.mock('../../src/utils/parseApiError', () => ({
  parseApiError: (...args: any[]) => parseApiError(...args),
}))

vi.mock('../../src/queries/news', () => ({
  useNewsPollQuery: () => ({ data: pollData }),
  useCreateNewsPollMutation: () => ({ mutateAsync: createMutateAsync }),
  useUpdateNewsPollMutation: () => ({ mutateAsync: updateMutateAsync }),
  useDeleteNewsPollMutation: () => ({ mutateAsync: deleteMutateAsync }),
}))

async function setupHost(newsId = 'news-1', hasPoll = true) {
  const nid = ref<string | undefined>(newsId)
  const hp = ref<boolean | undefined>(hasPoll)
  let api: any = null
  const mod = await import('../../src/components/news/poll-panel/composables/usePollPanelState')
  const Host = defineComponent({
    setup() {
      api = mod.usePollPanelState(nid, hp)
      return () => h('div')
    },
  })
  mount(Host)
  return { api, nid, hp }
}

describe('cov-feat usePollPanelState', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    pollData.value = null
  })

  it('makeEmptyQuestion returns expected defaults', async () => {
    const mod = await import('../../src/components/news/poll-panel/composables/usePollPanelState')
    const q = mod.makeEmptyQuestion(3)
    expect(q.sort_order).toBe(3)
    expect(q.options).toHaveLength(2)
    expect(q.is_required).toBe(true)
    expect(q.is_multiple).toBe(false)
  })

  it('initializes create form and cancel resets it', async () => {
    const { api } = await setupHost('news-1', false)
    expect(api.showCreateForm.value).toBe(false)
    expect(api.pollForm.value.questions.length).toBe(1)

    api.initCreateForm()
    expect(api.showCreateForm.value).toBe(true)

    api.pollForm.value.questions[0].text = 'changed'
    api.cancelCreate()
    expect(api.showCreateForm.value).toBe(false)
    expect(api.pollForm.value.questions[0].text).toBe('')
  })

  it('hydrates from poll and computes hasVotes', async () => {
    pollData.value = {
      is_anonymous: false,
      allow_revote: true,
      results_visibility: 'always',
      closes_at: '2026-01-01T10:00:00.000Z',
      total_voters: 2,
      questions: [
        {
          id: 'q2',
          text: 'B',
          sort_order: 2,
          is_required: true,
          is_multiple: true,
          max_choices: 3,
          allow_custom_answer: true,
          options: [
            { id: 'o2', text: '2', image_url: '', sort_order: 2 },
            { id: 'o1', text: '1', image_url: '', sort_order: 1 },
          ],
        },
      ],
    }

    const { api } = await setupHost('news-1', true)
    expect(api.hasVotes.value).toBe(true)
    expect(api.pollForm.value.is_anonymous).toBe(false)
    expect(api.pollForm.value.questions[0].options[0].id).toBe('o1')
  })

  it('handles option image upload guard/success/error', async () => {
    const { api, nid } = await setupHost('news-1', false)
    const opt = { text: 'x', image_url: '', sort_order: 0 }
    const onFinish = vi.fn()
    const onError = vi.fn()

    nid.value = undefined
    await api.handleOptionImageUpload(opt, { file: { file: new File(['x'], 'x.png') }, onFinish, onError } as any)
    expect(onError).toHaveBeenCalledTimes(1)

    nid.value = 'news-1'
    uploadNewsInlineMedia.mockResolvedValueOnce({ url: 'https://cdn/img.png' })
    await api.handleOptionImageUpload(opt, { file: { file: new File(['x'], 'x.png') }, onFinish, onError } as any)
    expect(opt.image_url).toBe('https://cdn/img.png')
    expect(onFinish).toHaveBeenCalled()

    uploadNewsInlineMedia.mockRejectedValueOnce(new Error('boom'))
    await api.handleOptionImageUpload(opt, { file: { file: new File(['x'], 'x.png') }, onFinish, onError } as any)
    expect(msg.error).toHaveBeenCalledWith('parsed-upload-error')
  })

  it('validates before save and returns early on invalid data or missing newsId', async () => {
    const { api, nid } = await setupHost('news-1', false)

    api.pollForm.value.questions = []
    await api.handleSave()
    expect(msg.error).toHaveBeenCalledWith('news.poll.editor.minQuestions')

    api.pollForm.value.questions = [{
      text: 'Q',
      sort_order: 0,
      is_required: true,
      is_multiple: false,
      max_choices: null,
      allow_custom_answer: false,
      options: [{ text: 'A', image_url: '', sort_order: 0 }, { text: 'A', image_url: '', sort_order: 1 }],
    }]
    await api.handleSave()
    expect(msg.error).toHaveBeenCalledWith('news.poll.editor.duplicateOptions')

    api.pollForm.value.questions[0].options = [{ text: '', image_url: '', sort_order: 0 }, { text: 'B', image_url: '', sort_order: 1 }]
    await api.handleSave()
    expect(msg.error).toHaveBeenCalledWith('news.poll.editor.optionTextOrImage')

    api.pollForm.value.questions[0].options = [{ text: 'A', image_url: '', sort_order: 0 }, { text: 'B', image_url: '', sort_order: 1 }]
    nid.value = undefined
    await api.handleSave()
    expect(createMutateAsync).not.toHaveBeenCalled()
  })

  it('saves by create path and update path and handles save error', async () => {
    const { api } = await setupHost('news-1', false)
    api.pollForm.value.questions = [{
      id: 'q1',
      text: ' Q ',
      sort_order: 9,
      is_required: true,
      is_multiple: true,
      max_choices: 2,
      allow_custom_answer: false,
      options: [{ id: 'o1', text: ' A ', image_url: ' ', sort_order: 3 }, { id: 'o2', text: 'B', image_url: 'img', sort_order: 2 }],
    }]

    createMutateAsync.mockResolvedValueOnce({})
    api.showCreateForm.value = true
    await api.handleSave()
    expect(createMutateAsync).toHaveBeenCalled()
    expect(api.showCreateForm.value).toBe(false)
    expect(msg.success).toHaveBeenCalledWith('common.save')

    pollData.value = {
      is_anonymous: true,
      allow_revote: false,
      results_visibility: 'after_vote',
      closes_at: null,
      total_voters: 0,
      questions: [{ ...api.pollForm.value.questions[0], options: [{ id: 'o1', text: 'A', image_url: '', sort_order: 0 }, { id: 'o2', text: 'B', image_url: '', sort_order: 1 }] }],
    }
    const s2 = await setupHost('news-1', true)
    updateMutateAsync.mockResolvedValueOnce({})
    await s2.api.handleSave()
    expect(updateMutateAsync).toHaveBeenCalled()

    updateMutateAsync.mockRejectedValueOnce({ response: { _data: { detail: 'save fail' } } })
    await s2.api.handleSave()
    expect(msg.error).toHaveBeenCalledWith('save fail')
  })

  it('deletes with guard, cancel confirm, success and error paths', async () => {
    const { api, nid } = await setupHost('news-1', true)

    nid.value = undefined
    await api.handleDelete()
    expect(confirm).not.toHaveBeenCalled()

    nid.value = 'news-1'
    confirm.mockResolvedValueOnce(false)
    await api.handleDelete()
    expect(deleteMutateAsync).not.toHaveBeenCalled()

    confirm.mockResolvedValueOnce(true)
    deleteMutateAsync.mockResolvedValueOnce({})
    await api.handleDelete()
    expect(deleteMutateAsync).toHaveBeenCalledWith('news-1')
    expect(msg.success).toHaveBeenCalledWith('news.poll.actions.deleted:"Опрос удалён"')

    confirm.mockResolvedValueOnce(true)
    deleteMutateAsync.mockRejectedValueOnce({ message: 'cannot delete' })
    await api.handleDelete()
    expect(msg.error).toHaveBeenCalledWith('cannot delete')
  })
})
