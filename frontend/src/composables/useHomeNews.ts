import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useNewsListQuery, useNewsCategoriesQuery } from '../queries/news'
import type { News } from '../api/news'

export function useHomeNews() {
  const router = useRouter()

  const newsQuery = useNewsListQuery({ page: 1, page_size: 5 })
  const categoriesQuery = useNewsCategoriesQuery()

  const loadingNews = computed(() => newsQuery.isLoading.value)
  const news = computed<News[]>(() => newsQuery.data.value?.items ?? [])
  const totalNews = computed(() => newsQuery.data.value?.total ?? 0)

  const pinned = computed(() => news.value.filter(n => n.is_pinned).slice(0, 1))
  // 3 карточки = один полный ряд сетки 3×N. Раньше было 4 → второй ряд с 1
  // карточкой и 2 пустыми слотами (+278px высоты дашборда впустую).
  const regular = computed(() => news.value.filter(n => !n.is_pinned).slice(0, 3))
  const categoriesMap = computed<Record<string, string>>(() =>
    Object.fromEntries((categoriesQuery.data.value ?? []).map(c => [c.name, c.color]))
  )

  function goToNews(id: string) {
    router.push(`/news/${id}`)
  }

  return { loadingNews, news, totalNews, pinned, regular, categoriesMap, goToNews }
}
