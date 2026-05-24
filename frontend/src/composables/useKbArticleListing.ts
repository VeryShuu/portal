import { computed, ref, watch, type Ref } from 'vue'
import { useDebounceFn } from './useDebounceFn'
import { useKbArticlesQuery, useKbTagsQuery } from '../queries/kb'
import type { KbArticleListItem, KbTag } from '../api/kb'

export interface UseKbArticleListingOptions {
  selectedSection: Ref<string | null>
  pageSize?: number
  debounceMs?: number
}

export function useKbArticleListing(opts: UseKbArticleListingOptions) {
  const pageSize = opts.pageSize ?? 20
  const debounceMs = opts.debounceMs ?? 400

  const page = ref(1)
  const searchQuery = ref('')
  const debouncedQuery = ref('')
  const statusFilter = ref<string | null>(null)
  const tagFilter = ref<string | null>(null)

  watch([opts.selectedSection, statusFilter, tagFilter], () => {
    page.value = 1
  })

  const applySearch = useDebounceFn(() => {
    page.value = 1
    debouncedQuery.value = searchQuery.value
  }, debounceMs)

  const articlesParams = computed(() => ({
    section_id: opts.selectedSection.value ?? undefined,
    q: debouncedQuery.value || undefined,
    status: statusFilter.value ?? undefined,
    tag: tagFilter.value ?? undefined,
    limit: pageSize,
    offset: (page.value - 1) * pageSize,
  }))

  const { data: articlesData, isLoading: loading } = useKbArticlesQuery(articlesParams)
  const { data: allTags } = useKbTagsQuery()

  const articles = computed<KbArticleListItem[]>(() => articlesData.value?.items ?? [])
  const total = computed(() => articlesData.value?.total ?? 0)

  const tagOptions = computed(() =>
    (allTags.value ?? []).map((tg: KbTag) => ({ label: tg.name, value: tg.slug })),
  )

  function selectTag(slug: string) {
    page.value = 1
    tagFilter.value = tagFilter.value === slug ? null : slug
  }

  function onSearchInput() {
    applySearch()
  }

  return {
    page,
    pageSize,
    searchQuery,
    statusFilter,
    tagFilter,
    articles,
    total,
    loading,
    tagOptions,
    selectTag,
    onSearchInput,
  }
}
