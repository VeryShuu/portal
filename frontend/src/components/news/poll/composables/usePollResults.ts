import { computed } from 'vue'
import type { Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { NewsPollPublic, NewsPollQuestionPublic, NewsPollOptionPublic } from '../../../../api/news'

export function usePollResults(poll: Ref<NewsPollPublic | null | undefined>) {
  const { t, locale } = useI18n()

  const sortedQuestions = computed<NewsPollQuestionPublic[]>(() => {
    if (!poll.value?.questions) return []
    return [...poll.value.questions].sort((a, b) => a.sort_order - b.sort_order)
  })

  function sortedOptions(q: NewsPollQuestionPublic): NewsPollOptionPublic[] {
    return [...q.options].sort((a, b) => a.sort_order - b.sort_order)
  }

  function questionHasImages(q: NewsPollQuestionPublic): boolean {
    return q.options.some(o => !!o.image_url)
  }

  const canReopen = computed(() => {
    if (!poll.value?.closes_at) return true
    return new Date(poll.value.closes_at) > new Date()
  })

  const closesAtText = computed(() => {
    if (!poll.value?.closes_at) return ''
    const date = new Date(poll.value.closes_at)
    const lang = locale.value === 'ru' ? 'ru-RU' : 'en-US'
    return date.toLocaleString(lang, {
      day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
    })
  })

  const resultsHiddenLabel = computed(() => {
    if (!poll.value) return ''
    const vis = poll.value.results_visibility
    if (vis === 'after_vote') return t('news.poll.resultsAfterVote')
    if (vis === 'after_close') return t('news.poll.resultsAfterClose')
    if (vis === 'only_admin_editor') return t('news.poll.resultsAdminOnly')
    return ''
  })

  function formatVotedAt(value: string): string {
    if (!value) return ''
    const date = new Date(value)
    const lang = locale.value === 'ru' ? 'ru-RU' : 'en-US'
    return date.toLocaleString(lang, {
      day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
    })
  }

  return {
    sortedQuestions,
    sortedOptions,
    questionHasImages,
    canReopen,
    closesAtText,
    resultsHiddenLabel,
    formatVotedAt,
  }
}
