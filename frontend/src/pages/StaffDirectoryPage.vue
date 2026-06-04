<template>
  <div class="staff-wrap u-page-wrap u-page-wrap--wide">
    <div class="page-head u-page-head">
      <div class="page-head__left">
        <h1 class="page-head__title">
          {{ t('staff.title') }}
        </h1>
        <div class="page-head__sub">
          {{ t('staff.pageSub') }}
        </div>
      </div>
      <div class="page-head__right">
        <span class="staff-total">{{ t('staff.total', { count: total }) }}</span>
      </div>
    </div>

    <StaffFilters
      :search-input="filters.searchInput.value"
      :department-filter="filters.departmentFilter.value"
      :office-filter="filters.officeFilter.value"
      :department-options="departmentOptions"
      :office-options="officeOptions"
      :has-active-filters="filters.hasActiveFilters.value"
      :view="view"
      :effective-view="effectiveView"
      :is-mobile="isMobile"
      :is-admin="isAdmin"
      :edit-mode="edit.editMode.value"
      :dirty="edit.dirty.value"
      :saving="edit.saving.value"
      @change-search="onSearchChange"
      @change-department="onDepartmentChange"
      @change-office="onOfficeChange"
      @reset="filters.resetFilters"
      @set-view="setView"
      @enter-edit="edit.enterEdit"
      @export="onExport"
      @print="onPrint"
      @cancel-edit="edit.cancelEdit"
      @save-edit="edit.saveEdit"
    />

    <div
      v-if="edit.editMode.value"
      class="staff-edit__hint"
    >
      {{ t('staff.edit.hint') }}
    </div>

    <div class="staff-content">
      <template v-if="isInitialLoading">
        <div
          v-if="effectiveView === 'grid' && !edit.editMode.value"
          class="staff-grid"
        >
          <SkeletonCard
            v-for="i in 6"
            :key="`sk-${i}`"
            variant="article"
          />
        </div>
        <div
          v-else
          class="staff-table-wrap"
        >
          <table class="staff-table">
            <thead>
              <tr>
                <th>{{ t('staff.fields.fullName') }}</th>
                <th class="cell-position">
                  {{ t('staff.fields.position') }}
                </th>
                <th class="cell-internal">
                  {{ t('staff.fields.internalPhone') }}
                </th>
                <th>{{ t('staff.fields.mobilePhone') }}</th>
                <th>{{ t('staff.fields.email') }}</th>
                <th class="cell-office">
                  {{ t('staff.fields.office') }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="i in 8"
                :key="`skr-${i}`"
                class="staff-skeleton-row"
              >
                <td colspan="6">
                  <div class="skeleton-bar" />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>

      <EmptyState
        v-else-if="isEmpty"
        variant="search"
        :title="t('staff.empty')"
        :description="t('staff.emptyHint')"
      >
        <template
          v-if="!edit.editMode.value && filters.hasActiveFilters.value"
          #action
        >
          <div class="staff-empty-chips">
            <n-button
              v-if="filters.departmentFilter.value"
              size="small"
              @click="clearDepartmentFilter"
            >
              {{ t('staff.chips.clearDepartment') }}
            </n-button>
            <n-button
              v-if="filters.officeFilter.value"
              size="small"
              @click="clearOfficeFilter"
            >
              {{ t('staff.chips.clearOffice') }}
            </n-button>
            <n-button
              size="small"
              type="primary"
              @click="filters.resetFilters"
            >
              {{ t('staff.chips.resetAll') }}
            </n-button>
          </div>
        </template>
      </EmptyState>

      <StaffEditView
        v-else-if="edit.editMode.value"
        :edit-groups="edit.editGroups.value"
        @toggle-user-hidden="edit.toggleUserHidden"
        @root-ready="onEditRootReady"
      />

      <StaffTableView
        v-else-if="effectiveView === 'table'"
        :table-groups="tableGroups"
        :hl="hl"
        :is-fetching="isFetching"
      />

      <StaffGridView
        v-else
        :users="readOnlyUsers"
        :hl="hl"
        :attribute-schema="attributeSchema"
        :lang="locale === 'en' ? 'en' : 'ru'"
        :is-fetching="isFetching"
      />

      <n-pagination
        v-if="!edit.editMode.value && total > pageSize"
        v-model:page="filters.page.value"
        :page-count="Math.ceil(total / pageSize)"
        :page-slot="7"
        class="staff-pagination"
        @update:page="filters.onPageChange"
      />
    </div>

    <transition name="staff-savebar">
      <div
        v-if="edit.editMode.value && edit.dirty.value"
        class="staff-savebar"
        role="region"
        :aria-label="t('staff.edit.unsaved')"
      >
        <span
          class="staff-savebar__dot"
          aria-hidden="true"
        />
        <span class="staff-savebar__text">{{ t('staff.edit.unsaved') }}</span>
        <div class="staff-savebar__spacer" />
        <n-button
          size="small"
          :disabled="edit.saving.value"
          @click="edit.cancelEdit"
        >
          {{ t('staff.edit.discard') }}
        </n-button>
        <n-button
          size="small"
          type="primary"
          :loading="edit.saving.value"
          @click="edit.saveEdit"
        >
          {{ t('staff.edit.save') }}
        </n-button>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NPagination } from 'naive-ui'
import EmptyState from '../components/EmptyState.vue'
import SkeletonCard from '../components/SkeletonCard.vue'
import StaffFilters from '../components/staff/StaffFilters.vue'
import StaffTableView from '../components/staff/StaffTableView.vue'
import StaffGridView from '../components/staff/StaffGridView.vue'
import StaffEditView from '../components/staff/StaffEditView.vue'
import { type UserPublic } from '../api/users'
import {
  useStaffListQuery,
  useUserAttributeSchemaQuery,
  useUserDepartmentsQuery,
  useUserOfficesQuery,
} from '../queries/users'
import { useHighlight } from '../composables/useHighlight'
import { useStaffFilters } from '../composables/useStaffFilters'
import { useStaffEdit } from '../composables/useStaffEdit'
import { useStaffView } from '../composables/useStaffView'
import { useStaffExport } from '../composables/useStaffExport'
import { useStaffLeaveGuard } from '../composables/useStaffLeaveGuard'
import { useAuthStore } from '../stores/auth'

const PAGE_SIZE = 100

const { t, locale } = useI18n()
const auth = useAuthStore()

const isAdmin = computed(() => auth.isAdmin)

const filters = useStaffFilters()
const editRootRef = ref<HTMLElement | null>(null)
const edit = useStaffEdit({ editRootRef })

function onEditRootReady(el: HTMLElement | null) {
  editRootRef.value = el
  if (!el) edit.destroySortables()
}

const pageSize = PAGE_SIZE

const { view, effectiveView, setView, isMobile } = useStaffView()

const queryParams = computed(() => ({
  q: filters.q.value || undefined,
  department: filters.departmentFilter.value || undefined,
  office: filters.officeFilter.value || undefined,
  sort: 'staff_custom' as const,
  page: filters.page.value,
  page_size: pageSize,
}))

const staffQuery = useStaffListQuery(queryParams)
const departmentsQuery = useUserDepartmentsQuery({ ordered: true })
const officesQuery = useUserOfficesQuery()
const schemaQuery = useUserAttributeSchemaQuery()

const readOnlyUsers = computed<UserPublic[]>(() => staffQuery.data.value?.items ?? [])

const total = computed<number>(() => {
  if (edit.editMode.value) {
    return edit.editGroups.value.reduce((s, g) => s + g.users.length, 0)
  }
  return staffQuery.data.value?.total ?? 0
})

const isInitialLoading = computed(
  () => !edit.editMode.value && staffQuery.isLoading.value && !staffQuery.data.value,
)
const isFetching = computed(
  () => !edit.editMode.value && staffQuery.isFetching.value && !!staffQuery.data.value,
)
const isEmpty = computed(() => {
  if (edit.editMode.value) return edit.editGroups.value.length === 0
  return readOnlyUsers.value.length === 0
})

const attributeSchema = computed(() => schemaQuery.data.value?.items ?? [])

const departmentOptions = computed(() =>
  (departmentsQuery.data.value?.items ?? []).map((d) => ({ label: d, value: d })),
)
const officeOptions = computed(() =>
  (officesQuery.data.value?.items ?? []).map((o) => ({ label: o, value: o })),
)

const hl = useHighlight(filters.q)

const tableGroups = computed(() => {
  if (filters.departmentFilter.value) {
    return [{ key: '__flat__', label: null as string | null, users: readOnlyUsers.value }]
  }
  const groups = new Map<string, { key: string; label: string | null; users: UserPublic[] }>()
  for (const u of readOnlyUsers.value) {
    const dept = u.department?.trim() || '—'
    if (!groups.has(dept)) groups.set(dept, { key: dept, label: dept, users: [] })
    groups.get(dept)!.users.push(u)
  }
  return Array.from(groups.values())
})

const { onExport, onPrint } = useStaffExport({
  q: computed(() => filters.q.value || undefined),
  department: filters.departmentFilter,
  office: filters.officeFilter,
})

useStaffLeaveGuard({ editMode: edit.editMode, dirty: edit.dirty })

function onSearchChange(v: string) {
  filters.searchInput.value = v
  filters.onSearchInput()
}

function onDepartmentChange(v: string | null) {
  filters.departmentFilter.value = v
  filters.onFilterChange()
}

function onOfficeChange(v: string | null) {
  filters.officeFilter.value = v
  filters.onFilterChange()
}

function clearDepartmentFilter() {
  filters.departmentFilter.value = null
  filters.onFilterChange()
}

function clearOfficeFilter() {
  filters.officeFilter.value = null
  filters.onFilterChange()
}

onMounted(() => {
  filters.syncToUrl()
})

onBeforeUnmount(() => {
  edit.destroySortables()
})
</script>

<style scoped>
.staff-wrap {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding-bottom: 32px;
}
.page-head__title {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  color: var(--color-text);
}
.page-head__sub {
  font-size: 13px;
  color: var(--color-text-muted);
  margin-top: 2px;
}
.staff-total {
  font-size: 13px;
  color: var(--color-text-muted);
  font-weight: 500;
}

.staff-edit__hint {
  padding: 8px 12px;
  background: var(--color-surface, #fafafa);
  border: 1px dashed var(--n-border-color, rgba(0, 0, 0, 0.12));
  border-radius: 6px;
  font-size: 13px;
  color: var(--color-text-muted);
}

.staff-content {
  position: relative;
}

.staff-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}

.staff-table-wrap {
  overflow-x: auto;
  border: 1px solid var(--n-border-color, rgba(0, 0, 0, 0.08));
  border-radius: 8px;
}
.staff-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}
.staff-table thead th {
  position: sticky;
  top: 0;
  background: var(--color-surface, #fafafa);
  text-align: left;
  font-weight: 600;
  font-size: 13px;
  color: var(--color-text-muted);
  padding: 10px 12px;
  border-bottom: 1px solid var(--n-border-color, rgba(0, 0, 0, 0.08));
  z-index: 1;
}

.staff-skeleton-row td { padding: 12px; }
.skeleton-bar {
  height: 14px;
  border-radius: 4px;
  background: linear-gradient(
    90deg,
    rgba(0,0,0,0.06) 0%,
    rgba(0,0,0,0.12) 50%,
    rgba(0,0,0,0.06) 100%
  );
  background-size: 200% 100%;
  animation: skeleton-shimmer 1.4s ease-in-out infinite;
}
@keyframes skeleton-shimmer {
  from { background-position: 200% 0; }
  to { background-position: -200% 0; }
}

.staff-pagination {
  margin-top: 20px;
  justify-content: center;
}

.staff-empty-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
}

.staff-savebar {
  position: fixed;
  left: 50%;
  bottom: 16px;
  transform: translateX(-50%);
  z-index: 100;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  background: var(--color-bg, #fff);
  border: 1px solid var(--n-border-color, rgba(0, 0, 0, 0.1));
  border-radius: 999px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.14), 0 1px 3px rgba(0, 0, 0, 0.06);
  min-width: 320px;
  max-width: calc(100vw - 32px);
}
.staff-savebar__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-warning, #d97706);
  box-shadow: 0 0 0 4px rgba(217, 119, 6, 0.16);
}
.staff-savebar__text {
  font-size: 13px;
  color: var(--color-text);
  font-weight: 500;
}
.staff-savebar__spacer { flex: 1 1 auto; }

.staff-savebar-enter-active,
.staff-savebar-leave-active {
  transition: transform 0.2s ease, opacity 0.2s ease;
}
.staff-savebar-enter-from,
.staff-savebar-leave-to {
  transform: translate(-50%, 40px);
  opacity: 0;
}

@media (max-width: 1024px) {
  .cell-office { display: none; }
}
@media (max-width: 768px) {
  .cell-internal,
  .cell-department { display: none; }
}
@media (max-width: 480px) {
  .cell-position { display: none; }
}

@media print {
  :deep(.app-header),
  :deep(.app-sidebar),
  :deep(.layout__sidebar),
  :deep(.layout__header),
  .staff-pagination,
  .staff-savebar {
    display: none !important;
  }
  .staff-row { break-inside: avoid; page-break-inside: avoid; }
  a { color: inherit; text-decoration: none; }
}
</style>
