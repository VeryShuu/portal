import { computed } from 'vue'
import type { SelectOption } from 'naive-ui'
import { useNewsCategoriesQuery, useNewsUploadLimitsQuery } from '../../queries/news'

export function useNewsFormOptions(
  t: (key: string, values?: Record<string, unknown>) => string,
) {
  const { data: categoriesData } = useNewsCategoriesQuery()
  const categoryOptions = computed<SelectOption[]>(() =>
    (categoriesData.value ?? []).map(c => ({ label: c.name, value: c.name })),
  )

  const { data: uploadLimitsData } = useNewsUploadLimitsQuery()
  const coverMaxSizeMb = computed(() => uploadLimitsData.value?.news_attachment_max_size_mb ?? 50)

  const statusOptions = computed(() => [
    { label: t('news.status.draft'), value: 'draft' },
    { label: t('news.status.published'), value: 'published' },
  ])

  return { categoryOptions, coverMaxSizeMb, statusOptions }
}
