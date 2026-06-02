import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { fetchNewsList, fetchNewsCategories, type News, type NewsCategory } from '../api/news'

export function useHomeNews() {
  const router = useRouter()

  const loadingNews = ref(true)
  const news = ref<News[]>([])
  const totalNews = ref(0)
  const newsCategories = ref<NewsCategory[]>([])

  const pinned = computed(() => news.value.filter(n => n.is_pinned).slice(0, 1))
  const regular = computed(() => news.value.filter(n => !n.is_pinned).slice(0, 4))
  const categoriesMap = computed<Record<string, string>>(() =>
    Object.fromEntries(newsCategories.value.map(c => [c.name, c.color]))
  )

  onMounted(async () => {
    try {
      const [newsResult, catsResult] = await Promise.allSettled([
        fetchNewsList({ page: 1, page_size: 5 }),
        fetchNewsCategories(),
      ])
      if (newsResult.status === 'fulfilled') {
        news.value = newsResult.value.items
        totalNews.value = newsResult.value.total
      }
      if (catsResult.status === 'fulfilled') {
        newsCategories.value = catsResult.value
      }
    } finally {
      loadingNews.value = false
    }
  })

  function goToNews(id: string) {
    router.push(`/news/${id}`)
  }

  return { loadingNews, news, totalNews, pinned, regular, categoriesMap, goToNews }
}
