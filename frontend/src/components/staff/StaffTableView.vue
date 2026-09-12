<template>
  <div
    class="staff-table-wrap"
    :class="{ 'is-fetching': isFetching }"
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
          <th class="cell-mobile">
            {{ t('staff.fields.mobilePhone') }}
          </th>
          <th>{{ t('staff.fields.email') }}</th>
          <th class="cell-office">
            {{ t('staff.fields.office') }}
          </th>
        </tr>
      </thead>
      <tbody
        v-for="group in tableGroups"
        :key="group.key"
        :class="{ 'is-collapsed': isCollapsed(group.key) }"
      >
        <tr
          v-if="group.label !== null"
          class="staff-group-header"
          :class="{ 'is-collapsed': isCollapsed(group.key) }"
          tabindex="0"
          role="button"
          :aria-expanded="!isCollapsed(group.key)"
          @click="toggle(group.key)"
          @keydown.enter.prevent="toggle(group.key)"
          @keydown.space.prevent="toggle(group.key)"
        >
          <td colspan="6">
            <span
              class="staff-group-header__chevron"
              aria-hidden="true"
            >
              <n-icon :size="14">
                <ChevronDownOutline v-if="!isCollapsed(group.key)" />
                <ChevronForwardOutline v-else />
              </n-icon>
            </span>
            <span class="staff-group-header__label">{{ group.label }}</span>
            <span class="staff-group-header__count">{{ group.users.length }}</span>
          </td>
        </tr>
        <template v-if="!isCollapsed(group.key)">
          <StaffRow
            v-for="u in group.users"
            :key="u.id"
            :user="u"
            :hl="hl"
          />
        </template>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import { reactive } from 'vue'
import { useI18n } from 'vue-i18n'
import { NIcon } from 'naive-ui'
import { ChevronDownOutline, ChevronForwardOutline } from '@vicons/ionicons5'
import StaffRow from '../StaffRow.vue'
import type { UserPublic } from '../../api/users'

export interface StaffTableGroup {
  key: string
  label: string | null
  users: UserPublic[]
}

defineProps<{
  tableGroups: StaffTableGroup[]
  hl: (text: string | null | undefined) => string
  isFetching: boolean
}>()

const { t } = useI18n()

const STORAGE_KEY = 'staff:collapsed'

function readCollapsed(): Record<string, true> {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw)
    if (parsed && typeof parsed === 'object') return parsed as Record<string, true>
  } catch { /* ignore */ }
  return {}
}

const collapsed = reactive<Record<string, true>>(readCollapsed())

function persist() {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(collapsed))
  } catch { /* ignore */ }
}

function isCollapsed(key: string): boolean {
  return collapsed[key] === true
}

function toggle(key: string) {
  if (collapsed[key]) delete collapsed[key]
  else collapsed[key] = true
  persist()
}
</script>

<style scoped>
.staff-table-wrap {
  overflow-x: auto;
  border: 1px solid var(--n-border-color, rgba(0, 0, 0, 0.08));
  border-radius: 8px;
}
.staff-table-wrap.is-fetching {
  opacity: 0.6;
  pointer-events: none;
  transition: opacity 0.15s ease;
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
  z-index: 2;
}
.staff-group-header {
  cursor: pointer;
  user-select: none;
}
.staff-group-header td {
  position: sticky;
  top: 37px;
  padding: 10px 12px;
  background: var(--n-color-target, rgba(99, 102, 241, 0.06));
  font-weight: 700;
  font-size: 13px;
  color: var(--color-text);
  border-bottom: 1px solid var(--n-border-color, rgba(0, 0, 0, 0.08));
  border-top: 1px solid var(--n-border-color, rgba(0, 0, 0, 0.08));
  text-align: left;
  z-index: 1;
  break-after: avoid;
  page-break-after: avoid;
}
.staff-group-header:hover td {
  background: var(--n-color-target-hover, rgba(99, 102, 241, 0.1));
}
.staff-group-header:focus-visible {
  outline: none;
}
.staff-group-header:focus-visible td {
  box-shadow: inset 0 0 0 2px var(--n-color-primary, #2080f0);
}
.staff-group-header__chevron {
  display: inline-flex;
  vertical-align: middle;
  margin-right: 6px;
  color: var(--color-text-muted);
}
.staff-group-header__label {
  vertical-align: middle;
}
.staff-group-header__count {
  display: inline-block;
  margin-left: 8px;
  padding: 1px 8px;
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-muted);
  background: rgba(0, 0, 0, 0.06);
  border-radius: 999px;
  vertical-align: middle;
}

@media (min-width: 1280px) {
  .staff-table tbody:not(.is-collapsed) :deep(.staff-row):nth-of-type(even) {
    background-color: rgba(0, 0, 0, 0.02);
  }
  .staff-table tbody:not(.is-collapsed) :deep(.staff-row):nth-of-type(even):hover {
    background-color: var(--n-merged-color-hover, rgba(0, 0, 0, 0.04));
  }
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
  .staff-table { display: table !important; width: 100%; }
  .staff-group-header td {
    position: static !important;
    background: #f0f0f0 !important;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
    break-after: avoid;
    page-break-after: avoid;
  }
}
</style>
