import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useNewsListQuery, useNewsCategoriesQuery } from '../queries/news'
import type { News } from '../api/news'

export function useHomeNews() {
  const router = useRouter()

  // page_size 7: достаточно для 6 regular + возможный pinned (filter исключит pinned).
  const newsQuery = useNewsListQuery({ page: 1, page_size: 7 })
  const categoriesQuery = useNewsCategoriesQuery()

  const loadingNews = computed(() => newsQuery.isLoading.value)
  const news = computed<News[]>(() => newsQuery.data.value?.items ?? [])
  const totalNews = computed(() => newsQuery.data.value?.total ?? 0)

  const pinned = computed(() => news.value.filter(n => n.is_pinned).slice(0, 1))
  // 5 новостей + 6-я плитка «Смотреть все» = два полных ряда сетки 3×N (6 ячеек).
  const regular = computed(() => news.value.filter(n => !n.is_pinned).slice(0, 5))
  const categoriesMap = computed<Record<string, string>>(() =>
    Object.fromEntries((categoriesQuery.data.value ?? []).map(c => [c.name, c.color]))
  )

  function goToNews(id: string) {
    router.push(`/news/${id}`)
  }

  return { loadingNews, news, totalNews, pinned, regular, categoriesMap, goToNews }
}
