import { onMounted, ref, watch, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import { fetchComments, createComment, deleteComment, type KbComment } from '../api/kb'

export function useKbArticleComments(articleId: Ref<string>) {
  const { t } = useI18n()
  const message = useMessage()

  const comments = ref<KbComment[]>([])
  const total = ref(0)
  const submitting = ref(false)
  const newComment = ref('')

  async function load() {
    const id = articleId.value
    try {
      const res = await fetchComments(id, { limit: 50 })
      if (id !== articleId.value) return
      comments.value = res.items
      total.value = res.total
    } catch {
      message.error(t('common.error'))
    }
  }

  async function submit() {
    if (!newComment.value.trim()) return
    submitting.value = true
    try {
      await createComment(articleId.value, newComment.value.trim())
      newComment.value = ''
      await load()
    } catch {
      message.error(t('common.error'))
    } finally {
      submitting.value = false
    }
  }

  async function remove(commentId: string) {
    try {
      await deleteComment(articleId.value, commentId)
      await load()
    } catch {
      message.error(t('common.error'))
    }
  }

  onMounted(load)
  watch(articleId, load)

  return { comments, total, submitting, newComment, load, submit, remove }
}
