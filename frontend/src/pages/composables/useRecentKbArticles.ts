import { computed } from 'vue'
import { useKbArticlesQuery } from '../../queries/kb'

export function useRecentKbArticles() {
  const { data: kbArticlesData } = useKbArticlesQuery({ status: 'published', limit: 5 })
  const recentArticles = computed(() => kbArticlesData.value?.items ?? [])

  return { recentArticles }
}
