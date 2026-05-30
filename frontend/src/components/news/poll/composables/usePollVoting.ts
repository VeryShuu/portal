import { ref, computed, reactive, watch } from 'vue'
import type { Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import { useAuthStore } from '../../../../stores/auth'
import type { NewsPollPublic, NewsPollQuestionPublic, NewsPollAnswer } from '../../../../api/news'
import {
  useVoteNewsPollMutation,
  useRevokeNewsPollVoteMutation,
} from '../../../../queries/news'

export function usePollVoting(
  poll: Ref<NewsPollPublic | null | undefined>,
  newsId: () => string,
) {
  const { t } = useI18n()
  const message = useMessage()
  const auth = useAuthStore()

  const voteMutation = useVoteNewsPollMutation()
  const revokeMutation = useRevokeNewsPollVoteMutation()

  const selectedByQuestion = reactive<Record<string, string[]>>({})
  const customTexts = reactive<Record<string, string>>({})
  const customSelected = reactive<Record<string, boolean>>({})
  const submitting = ref(false)

  function resetSelectionFromPoll() {
    for (const k of Object.keys(selectedByQuestion)) delete selectedByQuestion[k]
    for (const k of Object.keys(customTexts)) delete customTexts[k]
    for (const k of Object.keys(customSelected)) delete customSelected[k]
    if (!poll.value) return
    const myAnswers = poll.value.my_vote?.answers ?? []
    for (const q of poll.value.questions) {
      const a = myAnswers.find(x => x.question_id === q.id)
      selectedByQuestion[q.id] = a ? [...a.option_ids] : []
      customTexts[q.id] = a?.custom_text || ''
      customSelected[q.id] = !!(a?.custom_text && a.custom_text.length > 0)
    }
  }

  watch(poll, () => {
    resetSelectionFromPoll()
  }, { immediate: true })

  const hasVoted = computed(() => !!poll.value?.my_vote)

  function isSelected(qid: string, optId: string): boolean {
    return (selectedByQuestion[qid] || []).includes(optId)
  }

  function hasCustomSelected(qid: string): boolean {
    return !!customSelected[qid]
  }

  function totalPicks(q: NewsPollQuestionPublic): number {
    return (selectedByQuestion[q.id]?.length || 0) + (customSelected[q.id] ? 1 : 0)
  }

  function handleOptionClick(q: NewsPollQuestionPublic, optId: string) {
    if (poll.value?.is_closed || !poll.value?.can_vote || !auth.isAuthenticated || hasVoted.value) return
    handleSelect(q, optId)
  }

  function handleSelect(q: NewsPollQuestionPublic, optId: string) {
    if (!poll.value) return
    const list = selectedByQuestion[q.id] || []
    if (q.is_multiple) {
      const idx = list.indexOf(optId)
      if (idx > -1) {
        list.splice(idx, 1)
      } else {
        const max = q.max_choices
        if (!max || totalPicks(q) < max) {
          list.push(optId)
        } else {
          message.warning(t('news.poll.maxChoices', { count: max }))
          return
        }
      }
      selectedByQuestion[q.id] = list
    } else {
      selectedByQuestion[q.id] = [optId]
      customSelected[q.id] = false
    }
  }

  function handleCustomToggle(q: NewsPollQuestionPublic) {
    if (q.is_multiple) {
      const next = !customSelected[q.id]
      if (next) {
        const max = q.max_choices
        if (max && totalPicks(q) >= max) {
          message.warning(t('news.poll.maxChoices', { count: max }))
          return
        }
      }
      customSelected[q.id] = next
    } else {
      customSelected[q.id] = true
      selectedByQuestion[q.id] = []
    }
  }

  function handleCustomInput(q: NewsPollQuestionPublic) {
    const v = (customTexts[q.id] || '').trim()
    if (v.length > 0 && !customSelected[q.id]) {
      handleCustomToggle(q)
    }
  }

  const canSubmit = computed(() => {
    if (!poll.value) return false
    for (const q of poll.value.questions) {
      const picks = totalPicks(q)
      if (q.is_required && picks === 0) return false
      if (customSelected[q.id] && !(customTexts[q.id] || '').trim()) return false
    }
    return poll.value.questions.some(q => totalPicks(q) > 0)
  })

  function buildAnswers(): NewsPollAnswer[] {
    if (!poll.value) return []
    const out: NewsPollAnswer[] = []
    for (const q of poll.value.questions) {
      const opts = selectedByQuestion[q.id] || []
      const custom = customSelected[q.id] ? (customTexts[q.id] || '').trim() : ''
      if (opts.length === 0 && !custom) {
        if (!q.is_required) continue
      }
      out.push({ question_id: q.id, option_ids: opts, custom_text: custom || null })
    }
    return out
  }

  async function submitVote() {
    if (!canSubmit.value) return
    submitting.value = true
    try {
      await voteMutation.mutateAsync({
        newsId: newsId(),
        dto: { answers: buildAnswers() },
      })
      message.success(t('common.success', 'Успешно'))
    } catch (err: unknown) {
      const e = err as { response?: { _data?: { detail?: string } }; message?: string }
      message.error(e?.response?._data?.detail || e?.message || 'Ошибка')
    } finally {
      submitting.value = false
    }
  }

  async function revokeVote() {
    submitting.value = true
    try {
      await revokeMutation.mutateAsync(newsId())
      resetSelectionFromPoll()
      message.success(t('common.success', 'Успешно'))
    } catch (err: unknown) {
      const e = err as { response?: { _data?: { detail?: string } }; message?: string }
      message.error(e?.response?._data?.detail || e?.message || 'Ошибка')
    } finally {
      submitting.value = false
    }
  }

  return {
    selectedByQuestion,
    customTexts,
    customSelected,
    submitting,
    hasVoted,
    isSelected,
    hasCustomSelected,
    totalPicks,
    handleOptionClick,
    handleSelect,
    handleCustomToggle,
    handleCustomInput,
    canSubmit,
    buildAnswers,
    submitVote,
    revokeVote,
    resetSelectionFromPoll,
  }
}
