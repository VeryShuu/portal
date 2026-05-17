import { computed, ref, watch } from 'vue'
import type { Ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useDebounceFn } from './useDebounceFn'

export interface UseStaffFiltersResult {
  searchInput: Ref<string>
  q: Ref<string>
  departmentFilter: Ref<string | null>
  officeFilter: Ref<string | null>
  page: Ref<number>
  hasActiveFilters: Ref<boolean>
  debouncedApplySearch: ReturnType<typeof useDebounceFn<[]>>
  onSearchInput: () => void
  onFilterChange: () => void
  resetFilters: () => void
  onPageChange: () => void
  syncToUrl: () => void
}

export function useStaffFilters(): UseStaffFiltersResult {
  const route = useRoute()
  const router = useRouter()

  const searchInput = ref<string>(
    typeof route.query.q === 'string' ? route.query.q : '',
  )
  const q = ref<string>(searchInput.value)
  const departmentFilter = ref<string | null>(
    typeof route.query.department === 'string' ? route.query.department : null,
  )
  const officeFilter = ref<string | null>(
    typeof route.query.office === 'string' ? route.query.office : null,
  )
  const page = ref<number>(
    typeof route.query.page === 'string'
      ? Math.max(1, Number(route.query.page) || 1)
      : 1,
  )

  const hasActiveFilters = computed(
    () => !!q.value || !!departmentFilter.value || !!officeFilter.value,
  )

  let internalUpdate = false

  function syncToUrl(): void {
    const next: Record<string, string> = {}
    if (q.value) next.q = q.value
    if (departmentFilter.value) next.department = departmentFilter.value
    if (officeFilter.value) next.office = officeFilter.value
    if (page.value > 1) next.page = String(page.value)
    internalUpdate = true
    void router.replace({ query: next }).finally(() => {
      internalUpdate = false
    })
  }

  const debouncedApplySearch = useDebounceFn(() => {
    q.value = searchInput.value.trim()
    page.value = 1
    syncToUrl()
  }, 300)

  function onSearchInput(): void {
    debouncedApplySearch()
  }

  function onFilterChange(): void {
    page.value = 1
    syncToUrl()
  }

  function resetFilters(): void {
    searchInput.value = ''
    q.value = ''
    departmentFilter.value = null
    officeFilter.value = null
    page.value = 1
    syncToUrl()
  }

  function onPageChange(): void {
    syncToUrl()
  }

  watch(
    () => route.query,
    (qry) => {
      if (internalUpdate) return
      const newQ = typeof qry.q === 'string' ? qry.q : ''
      const newDept = typeof qry.department === 'string' ? qry.department : null
      const newOffice = typeof qry.office === 'string' ? qry.office : null
      const newPage =
        typeof qry.page === 'string' ? Math.max(1, Number(qry.page) || 1) : 1
      if (newQ !== q.value) {
        q.value = newQ
        searchInput.value = newQ
      }
      if (newDept !== departmentFilter.value) departmentFilter.value = newDept
      if (newOffice !== officeFilter.value) officeFilter.value = newOffice
      if (newPage !== page.value) page.value = newPage
    },
  )

  return {
    searchInput,
    q,
    departmentFilter,
    officeFilter,
    page,
    hasActiveFilters,
    debouncedApplySearch,
    onSearchInput,
    onFilterChange,
    resetFilters,
    onPageChange,
    syncToUrl,
  }
}
