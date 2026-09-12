import { ref, computed, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import {
  useNewsCommentsQuery,
  useCreateNewsCommentMutation,
  useUpdateNewsCommentMutation,
  useDeleteNewsCommentMutation,
} from '../queries/news'

export function useNewsComments(newsId: Ref<string>) {
  const { t } = useI18n()
  const message = useMessage()

  const commentsQuery = useNewsCommentsQuery(newsId)
  const createMutation = useCreateNewsCommentMutation()
  const updateMutation = useUpdateNewsCommentMutation()
  const deleteMutation = useDeleteNewsCommentMutation()

  const comments = computed(() => commentsQuery.data.value?.items ?? [])
  const total = computed(() => commentsQuery.data.value?.total ?? 0)
  const submitting = computed(() => createMutation.isPending.value)
  const newComment = ref('')

  async function submit() {
    const body = newComment.value.trim()
    if (!body) return
    try {
      await createMutation.mutateAsync({ newsId: newsId.value, body })
      newComment.value = ''
    } catch {
      message.error(t('common.error'))
    }
  }

  async function edit(commentId: string, body: string): Promise<boolean> {
    const trimmed = body.trim()
    if (!trimmed) return false
    try {
      await updateMutation.mutateAsync({ newsId: newsId.value, commentId, body: trimmed })
      return true
    } catch {
      message.error(t('common.error'))
      return false
    }
  }

  async function remove(commentId: string) {
    try {
      await deleteMutation.mutateAsync({ newsId: newsId.value, commentId })
    } catch {
      message.error(t('common.error'))
    }
  }

  return { comments, total, submitting, newComment, submit, edit, remove }
}
