import { ref, computed, watch, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage, type UploadCustomRequestOptions } from 'naive-ui'
import { useConfirmDialog } from '../../../../composables/useConfirmDialog'
import {
  useNewsPollQuery,
  useCreateNewsPollMutation,
  useUpdateNewsPollMutation,
  useDeleteNewsPollMutation,
} from '../../../../queries/news'
import { uploadNewsInlineMedia } from '../../../../api/news'
import { parseApiError } from '../../../../utils/parseApiError'

export interface OptionForm {
  id?: string
  text: string
  image_url: string
  sort_order: number
}

export interface QuestionForm {
  id?: string
  text: string
  sort_order: number
  is_required: boolean
  is_multiple: boolean
  max_choices: number | null
  allow_custom_answer: boolean
  options: OptionForm[]
}

export interface PollForm {
  is_anonymous: boolean
  allow_revote: boolean
  results_visibility: 'always' | 'after_vote' | 'after_close' | 'only_admin_editor'
  closes_at: string | null
  questions: QuestionForm[]
}

export function makeEmptyQuestion(sort = 0): QuestionForm {
  return {
    text: '',
    sort_order: sort,
    is_required: true,
    is_multiple: false,
    max_choices: null,
    allow_custom_answer: false,
    options: [
      { text: '', image_url: '', sort_order: 0 },
      { text: '', image_url: '', sort_order: 1 },
    ],
  }
}

export function usePollPanelState(
  newsId: Ref<string | undefined>,
  hasPoll: Ref<boolean | undefined>,
) {
  const { t } = useI18n()
  const message = useMessage()
  const { confirm } = useConfirmDialog()

  const { data: poll } = useNewsPollQuery(() => newsId.value || '', {
    enabled: computed(() => !!newsId.value && !!hasPoll.value),
  })

  const createMutation = useCreateNewsPollMutation()
  const updateMutation = useUpdateNewsPollMutation()
  const deleteMutation = useDeleteNewsPollMutation()

  const showCreateForm = ref(false)
  const saving = ref(false)
  const deleting = ref(false)
  const uploadingImage = ref(false)

  const pollForm = ref<PollForm>({
    is_anonymous: true,
    allow_revote: false,
    results_visibility: 'after_vote',
    closes_at: null,
    questions: [],
  })

  const hasVotes = computed(() => !!poll.value && (poll.value.total_voters || 0) > 0)

  watch(poll, (p) => {
    if (p) {
      pollForm.value.is_anonymous = p.is_anonymous
      pollForm.value.allow_revote = p.allow_revote
      pollForm.value.results_visibility = p.results_visibility
      pollForm.value.closes_at = p.closes_at || null
      pollForm.value.questions = [...p.questions]
        .sort((a, b) => a.sort_order - b.sort_order)
        .map(q => ({
          id: q.id,
          text: q.text,
          sort_order: q.sort_order,
          is_required: q.is_required,
          is_multiple: q.is_multiple,
          max_choices: q.max_choices || null,
          allow_custom_answer: q.allow_custom_answer,
          options: [...q.options]
            .sort((a, b) => a.sort_order - b.sort_order)
            .map(o => ({
              id: o.id,
              text: o.text || '',
              image_url: o.image_url || '',
              sort_order: o.sort_order,
            })),
        }))
      showCreateForm.value = false
    } else {
      resetForm()
    }
  }, { immediate: true })

  function resetForm() {
    pollForm.value = {
      is_anonymous: true,
      allow_revote: false,
      results_visibility: 'after_vote',
      closes_at: null,
      questions: [makeEmptyQuestion(0)],
    }
  }

  function initCreateForm() {
    resetForm()
    showCreateForm.value = true
  }

  function cancelCreate() {
    showCreateForm.value = false
    resetForm()
  }

  async function handleOptionImageUpload(opt: OptionForm, options: UploadCustomRequestOptions) {
    const { file, onFinish, onError } = options
    if (!newsId.value || !file.file) { onError(); return }
    uploadingImage.value = true
    try {
      const res = await uploadNewsInlineMedia(newsId.value, file.file)
      opt.image_url = res.url
      onFinish()
    } catch (e) {
      message.error(parseApiError(e, t))
      onError()
    } finally {
      uploadingImage.value = false
    }
  }

  function validatePoll(): boolean {
    if (pollForm.value.questions.length < 1) {
      message.error(t('news.poll.editor.minQuestions'))
      return false
    }
    for (const q of pollForm.value.questions) {
      if (!q.text.trim()) {
        message.error(t('news.poll.editor.questionPlaceholder'))
        return false
      }
      if (q.options.length < 2) {
        message.error(t('news.poll.editor.minOptions'))
        return false
      }
      for (const opt of q.options) {
        if (!opt.text.trim() && !opt.image_url.trim()) {
          message.error(t('news.poll.editor.optionTextOrImage'))
          return false
        }
      }
      const texts = q.options.map(o => o.text.trim().toLowerCase()).filter(Boolean)
      if (new Set(texts).size !== texts.length) {
        message.error(t('news.poll.editor.duplicateOptions'))
        return false
      }
    }
    return true
  }

  async function handleSave() {
    if (!validatePoll() || !newsId.value) return

    saving.value = true
    try {
      const questions = pollForm.value.questions.map((q, qi) => ({
        id: q.id,
        text: q.text.trim(),
        sort_order: qi,
        is_required: q.is_required,
        is_multiple: q.is_multiple,
        max_choices: q.is_multiple ? q.max_choices : null,
        allow_custom_answer: q.allow_custom_answer,
        options: q.options.map((o, oi) => ({
          id: o.id,
          text: o.text.trim() || null,
          image_url: o.image_url.trim() || null,
          sort_order: oi,
        })),
      }))

      const dto = {
        is_anonymous: pollForm.value.is_anonymous,
        allow_revote: pollForm.value.allow_revote,
        results_visibility: pollForm.value.results_visibility,
        closes_at: pollForm.value.closes_at,
        questions,
      }

      if (poll.value) {
        await updateMutation.mutateAsync({ newsId: newsId.value, dto })
      } else {
        await createMutation.mutateAsync({ newsId: newsId.value, dto })
        showCreateForm.value = false
      }
      message.success(t('common.save'))
    } catch (err: unknown) {
      const e = err as { response?: { _data?: { detail?: string } }; message?: string }
      message.error(e?.response?._data?.detail || e?.message || 'Ошибка сохранения')
    } finally {
      saving.value = false
    }
  }

  async function handleDelete() {
    if (!newsId.value) return
    const ok = await confirm({
      title: t('news.poll.actions.delete'),
      content: t('news.poll.actions.deleteConfirm'),
      positiveText: t('common.delete', 'Удалить'),
      negativeText: t('common.cancel', 'Отмена'),
      type: 'error',
    })
    if (!ok) return

    deleting.value = true
    try {
      await deleteMutation.mutateAsync(newsId.value)
      showCreateForm.value = false
      resetForm()
      message.success(t('news.poll.actions.deleted', 'Опрос удалён'))
    } catch (err: unknown) {
      const e = err as { response?: { _data?: { detail?: string } }; message?: string }
      message.error(e?.response?._data?.detail || e?.message || 'Ошибка удаления')
    } finally {
      deleting.value = false
    }
  }

  return {
    poll,
    pollForm,
    showCreateForm,
    saving,
    deleting,
    uploadingImage,
    hasVotes,
    initCreateForm,
    cancelCreate,
    handleOptionImageUpload,
    handleSave,
    handleDelete,
  }
}
