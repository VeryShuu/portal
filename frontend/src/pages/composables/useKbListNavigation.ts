import { useRouter } from 'vue-router'

export function useKbListNavigation() {
  const router = useRouter()

  function openTrash() {
    router.push({ name: 'kb-trash' })
  }

  function openCreate(sectionId: string | null) {
    router.push({ path: '/kb/create', query: sectionId ? { section_id: sectionId } : {} })
  }

  function openArticle(id: string) {
    router.push(`/kb/articles/${id}`)
  }

  return { openTrash, openCreate, openArticle }
}
