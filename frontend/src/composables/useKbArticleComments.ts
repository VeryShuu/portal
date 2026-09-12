import { ref, computed, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import {
  useKbCommentsQuery,
  useCreateKbCommentMutation,
  useDeleteKbCommentMutation,
} from '../queries/kb'

export function useKbArticleComments(articleId: Ref<string>) {
  const { t } = useI18n()
  const message = useMessage()

  const commentsQuery = useKbCommentsQuery(articleId)
  const createMutation = useCreateKbCommentMutation()
  const deleteMutation = useDeleteKbCommentMutation()

  const comments = computed(() => commentsQuery.data.value?.items ?? [])
  const total = computed(() => commentsQuery.data.value?.total ?? 0)
  const submitting = computed(() => createMutation.isPending.value)
  const newComment = ref('')

  async function load() {
    await commentsQuery.refetch()
  }

  async function submit() {
    const body = newComment.value.trim()
    if (!body) return
    try {
      await createMutation.mutateAsync({ articleId: articleId.value, body })
      newComment.value = ''
    } catch {
      message.error(t('common.error'))
    }
  }

  async function remove(commentId: string) {
    try {
      await deleteMutation.mutateAsync({ articleId: articleId.value, commentId })
    } catch {
      message.error(t('common.error'))
    }
  }

  return { comments, total, submitting, newComment, load, submit, remove }
}
