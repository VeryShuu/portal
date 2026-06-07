import { describe, it, expect, vi, beforeEach } from 'vitest'
import { defineComponent, h, ref } from 'vue'
import { mount } from '@vue/test-utils'

const warning = vi.fn()
const success = vi.fn()
const error = vi.fn()

const voteMutateAsync = vi.fn()
const revokeMutateAsync = vi.fn()
const authState = { isAuthenticated: true }

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

vi.mock('naive-ui', () => ({
  useMessage: () => ({ warning, success, error }),
}))

vi.mock('../../src/stores/auth', () => ({
  useAuthStore: () => authState,
}))

vi.mock('../../src/queries/news', () => ({
  useVoteNewsPollMutation: () => ({ mutateAsync: voteMutateAsync }),
  useRevokeNewsPollVoteMutation: () => ({ mutateAsync: revokeMutateAsync }),
}))

async function setupHost(initialPoll: any) {
  const poll = ref<any>(initialPoll)
  let api: any = null
  const mod = await import('../../src/components/news/poll/composables/usePollVoting')
  const Host = defineComponent({
    setup() {
      api = mod.usePollVoting(poll, () => 'news-1')
      return () => h('div')
    },
  })
  mount(Host)
  return { api, poll }
}

const singleQ = {
  id: 'q1',
  text: 'q1',
  is_required: true,
  is_multiple: false,
  max_choices: null,
  sort_order: 0,
  options: [{ id: 'o1' }, { id: 'o2' }],
}

const multiQ = {
  id: 'q2',
  text: 'q2',
  is_required: false,
  is_multiple: true,
  max_choices: 2,
  sort_order: 1,
  options: [{ id: 'a' }, { id: 'b' }, { id: 'c' }],
}

describe('cov-feat usePollVoting', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    authState.isAuthenticated = true
  })

  it('hydrates state from poll and exposes selection helpers', async () => {
    const { api } = await setupHost({
      is_closed: false,
      can_vote: true,
      my_vote: {
        answers: [
          { question_id: 'q1', option_ids: ['o2'], custom_text: 'x' },
          { question_id: 'q2', option_ids: ['a'], custom_text: '' },
        ],
      },
      questions: [singleQ, multiQ],
    })

    expect(api.hasVoted.value).toBe(true)
    expect(api.isSelected('q1', 'o2')).toBe(true)
    expect(api.hasCustomSelected('q1')).toBe(true)
    expect(api.totalPicks(multiQ)).toBe(1)
  })

  it('selects single-choice and toggles custom for single-choice', async () => {
    const { api } = await setupHost({
      is_closed: false,
      can_vote: true,
      my_vote: null,
      questions: [singleQ],
    })

    api.customSelected.q1 = true
    api.handleSelect(singleQ as any, 'o1')
    expect(api.selectedByQuestion.q1).toEqual(['o1'])
    expect(api.customSelected.q1).toBe(false)

    api.handleCustomToggle(singleQ as any)
    expect(api.customSelected.q1).toBe(true)
    expect(api.selectedByQuestion.q1).toEqual([])
  })

  it('handles multiple-choice max limit and removal', async () => {
    const { api } = await setupHost({
      is_closed: false,
      can_vote: true,
      my_vote: null,
      questions: [multiQ],
    })

    api.handleSelect(multiQ as any, 'a')
    api.handleSelect(multiQ as any, 'b')
    api.handleSelect(multiQ as any, 'c')
    expect(api.selectedByQuestion.q2).toEqual(['a', 'b'])
    expect(warning).toHaveBeenCalledTimes(1)

    api.handleSelect(multiQ as any, 'a')
    expect(api.selectedByQuestion.q2).toEqual(['b'])

    api.customSelected.q2 = true
    api.handleCustomToggle(multiQ as any)
    expect(api.customSelected.q2).toBe(false)
  })

  it('guards option click by poll state/auth/voted', async () => {
    const { api, poll } = await setupHost({
      is_closed: false,
      can_vote: true,
      my_vote: null,
      questions: [singleQ],
    })

    api.handleOptionClick(singleQ as any, 'o1')
    expect(api.selectedByQuestion.q1).toEqual(['o1'])

    poll.value.is_closed = true
    api.handleOptionClick(singleQ as any, 'o2')
    expect(api.selectedByQuestion.q1).toEqual(['o1'])

    poll.value.is_closed = false
    poll.value.can_vote = false
    api.handleOptionClick(singleQ as any, 'o2')
    expect(api.selectedByQuestion.q1).toEqual(['o1'])

    poll.value.can_vote = true
    authState.isAuthenticated = false
    api.handleOptionClick(singleQ as any, 'o2')
    expect(api.selectedByQuestion.q1).toEqual(['o1'])

    authState.isAuthenticated = true
    poll.value.my_vote = { answers: [] }
    api.handleOptionClick(singleQ as any, 'o2')
    expect(api.selectedByQuestion.q1).toEqual(['o1'])
  })

  it('computes canSubmit and buildAnswers including optional/required behavior', async () => {
    const optionalQ = { ...multiQ, id: 'q3', is_required: false, max_choices: null }
    const requiredQ = { ...singleQ, id: 'q4', is_required: true }
    const { api } = await setupHost({
      is_closed: false,
      can_vote: true,
      my_vote: null,
      questions: [optionalQ, requiredQ],
    })

    expect(api.canSubmit.value).toBe(false)

    api.customSelected.q3 = true
    api.customTexts.q3 = ' '
    expect(api.canSubmit.value).toBe(false)

    api.customTexts.q3 = 'custom'
    api.handleSelect(requiredQ as any, 'o1')
    expect(api.canSubmit.value).toBe(true)

    expect(api.buildAnswers()).toEqual([
      { question_id: 'q3', option_ids: [], custom_text: 'custom' },
      { question_id: 'q4', option_ids: ['o1'], custom_text: null },
    ])
  })

  it('submitVote handles no-op, success and error branches', async () => {
    const { api } = await setupHost({
      is_closed: false,
      can_vote: true,
      my_vote: null,
      questions: [singleQ],
    })

    await api.submitVote()
    expect(voteMutateAsync).not.toHaveBeenCalled()

    api.handleSelect(singleQ as any, 'o1')
    voteMutateAsync.mockResolvedValueOnce({})
    await api.submitVote()
    expect(voteMutateAsync).toHaveBeenCalledWith({
      newsId: 'news-1',
      dto: { answers: [{ question_id: 'q1', option_ids: ['o1'], custom_text: null }] },
    })
    expect(success).toHaveBeenCalled()
    expect(api.submitting.value).toBe(false)

    voteMutateAsync.mockRejectedValueOnce({ response: { _data: { detail: 'bad vote' } } })
    await api.submitVote()
    expect(error).toHaveBeenCalledWith('bad vote')
    expect(api.submitting.value).toBe(false)
  })

  it('revokeVote handles success and error branches', async () => {
    const { api } = await setupHost({
      is_closed: false,
      can_vote: true,
      my_vote: {
        answers: [{ question_id: 'q1', option_ids: ['o2'], custom_text: '' }],
      },
      questions: [singleQ],
    })

    revokeMutateAsync.mockResolvedValueOnce({})
    await api.revokeVote()
    expect(revokeMutateAsync).toHaveBeenCalledWith('news-1')
    expect(success).toHaveBeenCalled()
    expect(api.submitting.value).toBe(false)

    revokeMutateAsync.mockRejectedValueOnce({ message: 'revoke fail' })
    await api.revokeVote()
    expect(error).toHaveBeenCalledWith('revoke fail')
    expect(api.submitting.value).toBe(false)
  })
})
