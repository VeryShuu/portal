<template>
  <div class="apr u-page-wrap">
    <header class="apr__head">
      <h1 class="u-page-head__title">
        {{ t('approvals.title') }}
      </h1>
      <p class="apr__hint">
        {{ t('approvals.subtitle') }}
      </p>
    </header>

    <div
      v-if="loading"
      class="apr__loader"
    >
      <n-spin />
    </div>

    <!-- Ошибка сети/5xx ≠ пустая очередь: явный error-state с повтором
         (ревью 2026-09-05 — ошибка списка выглядела как «нет документов»). -->
    <n-alert
      v-else-if="listError"
      type="error"
      :show-icon="true"
    >
      {{ t('approvals.listError') }}
      <n-button
        size="small"
        style="margin-left: 12px"
        @click="refresh"
      >
        {{ t('approvals.retry') }}
      </n-button>
    </n-alert>

    <EmptyState
      v-else-if="!filteredItems.length"
      :title="search ? t('approvals.searchEmpty') : t('approvals.empty')"
      :description="search ? t('approvals.searchEmptyHint') : t('approvals.emptyHint')"
    />

    <template v-else>
      <BulkApproveReport
        v-if="bulkReport"
        :approved="bulkReport.approved"
        :failed="bulkReport.failed"
        :rows="bulkReport.rows"
        @dismiss="dismissBulkReport"
      />

      <div class="apr__toolbar">
        <div class="apr__toolbar-left">
          <n-checkbox
            :checked="allSelected"
            @update:checked="toggleSelectAll"
          >
            {{ t('approvals.selectAll') }}
          </n-checkbox>
          <span
            v-if="selectedCount"
            class="apr__toolbar-count"
          >
            {{ t('approvals.selectedOf', { n: selectedCount, m: bulkEligible.length }) }}
          </span>
        </div>
        <n-button
          type="success"
          size="small"
          :disabled="!selectedCount"
          :loading="actionRunning"
          @click="bulkApproveSelected"
        >
          {{ t('approvals.bulkButton', { n: selectedCount }) }}
        </n-button>
      </div>

      <div class="apr__filters">
        <n-input
          v-model:value="search"
          size="small"
          clearable
          :placeholder="t('approvals.searchPlaceholder')"
          class="apr__search"
        />
        <n-button
          size="small"
          :loading="refreshing"
          @click="refresh"
        >
          <template #icon>
            <n-icon><RefreshOutline /></n-icon>
          </template>
          {{ t('approvals.refresh') }}
        </n-button>
      </div>

      <n-card
        v-for="doc in filteredItems"
        :key="doc.guid"
        class="apr__card"
        size="small"
        hoverable
      >
        <div class="apr__card-grid">
          <div class="apr__card-head">
            <n-checkbox
              v-if="doc.has_prices && !doc.requires_manager"
              class="apr__card-check"
              :checked="selected.has(doc.guid)"
              @update:checked="toggleSelected(doc.guid, $event)"
            />
            <n-tooltip
              v-else-if="doc.requires_manager"
              trigger="hover"
            >
              <template #trigger>
                <n-icon class="apr__card-lock">
                  <LockClosedOutline />
                </n-icon>
              </template>
              {{ t('approvals.requiresManagerTooltip') }}
            </n-tooltip>
            <!-- Внутренний заказ без требования ответственного: маркера нет —
                 из bulk исключён, согласуется в карточке (v2.1.0.0) -->

            <div class="apr__card-title">
              <strong class="apr__card-number">{{ doc.number }}</strong>
              <span class="apr__card-date">{{ shortDate(doc.date) }}</span>
              <span
                class="apr__card-type"
                :class="doc.has_prices ? 'apr__card-type--supplier' : 'apr__card-type--internal'"
                :title="typeLabel(doc)"
                :aria-label="typeLabel(doc)"
              >
                <n-icon size="19">
                  <StorefrontOutline v-if="doc.has_prices" />
                  <ArchiveOutline v-else />
                </n-icon>
              </span>
            </div>
          </div>

          <div class="apr__card-actions">
            <n-button
              size="small"
              @click="openDrawer(doc.guid)"
            >
              {{ t('approvals.details') }}
            </n-button>
            <n-button
              v-if="doc.has_prices && !doc.requires_manager"
              size="small"
              type="success"
              :loading="actionRunning"
              @click="quickApprove(doc)"
            >
              {{ t('approvals.actions.approve') }}
            </n-button>
          </div>

          <dl class="apr__props">
            <div class="apr__prop">
              <dt>{{ t('approvals.props.organization') }}</dt>
              <dd>{{ doc.organization }}</dd>
            </div>
            <div class="apr__prop">
              <dt>{{ doc.has_prices ? t('approvals.props.manager') : t('approvals.props.responsible') }}</dt>
              <dd>{{ doc.manager || '—' }}</dd>
            </div>
            <div
              v-if="doc.has_prices"
              class="apr__prop"
            >
              <dt>{{ t('approvals.props.contractor') }}</dt>
              <dd>{{ doc.contractor || '—' }}</dd>
            </div>
            <div
              v-if="doc.has_prices && doc.amount != null"
              class="apr__prop"
            >
              <dt>{{ t('approvals.props.amount') }}</dt>
              <dd class="apr__prop-amount">
                {{ formatAmount(doc.amount, locale) }} {{ doc.currency }}
              </dd>
            </div>
            <div
              v-if="doc.has_prices"
              class="apr__prop apr__prop--project"
            >
              <dt>{{ t('approvals.props.project') }}</dt>
              <dd :title="doc.project || undefined">
                {{ shortProject(doc.project) }}
              </dd>
            </div>
          </dl>
        </div>
      </n-card>
    </template>

    <ApprovalDetailDrawer
      :show="drawerOpen"
      :loading="detailLoading"
      :error="detailError"
      :running="actionRunning"
      :doc="detail"
      :comment="comment"
      :manager-guid="managerGuid"
      @close="closeDrawer"
      @retry="retryDetail"
      @update:comment="comment = $event"
      @update:manager-guid="managerGuid = $event"
      @approve="approveCurrent"
      @reject="rejectCurrent"
    />
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import {
  NAlert,
  NButton,
  NCard,
  NCheckbox,
  NIcon,
  NInput,
  NSpin,
  NTooltip,
} from 'naive-ui'
import {
  ArchiveOutline,
  LockClosedOutline,
  RefreshOutline,
  StorefrontOutline,
} from '@vicons/ionicons5'
import EmptyState from '../../components/EmptyState.vue'
import ApprovalDetailDrawer from '../../components/approvals/ApprovalDetailDrawer.vue'
import BulkApproveReport from '../../components/approvals/BulkApproveReport.vue'
import { useApprovalsPage } from '../composables/useApprovalsPage'
import { formatAmount } from '../../utils/formatAmount'
import type { ApprovalDocument } from '../../api/approvals'

const { t, locale } = useI18n()

const {
  filteredItems,
  loading,
  listError,
  refreshing,
  search,
  refresh,
  selected,
  selectedCount,
  allSelected,
  bulkEligible,
  toggleSelected,
  toggleSelectAll,
  bulkApproveSelected,
  bulkReport,
  dismissBulkReport,
  quickApprove,
  actionRunning,
  drawerOpen,
  detail,
  detailLoading,
  detailError,
  retryDetail,
  comment,
  managerGuid,
  openDrawer,
  closeDrawer,
  approveCurrent,
  rejectCurrent,
} = useApprovalsPage()

function typeLabel(doc: ApprovalDocument): string {
  return doc.has_prices ? t('approvals.types.supplier') : t('approvals.types.internal')
}

/** «04.09.2026 17:34:16» → «04.09.2026 17:34» — секунды в очереди шумят. */
function shortDate(date: string): string {
  return date.replace(/:\d{2}$/, '')
}

/** Проект длиннее 60 символов обрезаем (полный — в карточке и в title). */
const PROJECT_MAX_LENGTH = 60

function shortProject(project: string | null | undefined): string {
  if (!project) return '—'
  return project.length > PROJECT_MAX_LENGTH
    ? `${project.slice(0, PROJECT_MAX_LENGTH)}…`
    : project
}
</script>

<style scoped>
.apr__head {
  margin-bottom: 20px;
}
.apr__hint {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--color-text-muted);
}
.apr__loader {
  display: flex;
  justify-content: center;
  padding: 64px 0;
}

/* ── Тулбар выбора ─────────────────────────────────────────────── */
.apr__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px 12px;
  margin-bottom: 14px;
}
.apr__filters {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.apr__search {
  max-width: 320px;
}
.apr__toolbar-left {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.apr__toolbar-count {
  font-size: 13px;
  color: var(--color-text-muted);
}

/* ── Карточка: шапка + кнопки в одной строке, реквизиты ниже ───── */
.apr__card {
  margin-bottom: 12px;
}
.apr__card-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  grid-template-areas:
    'head actions'
    'props props';
  align-items: center;
  gap: 4px 12px;
}
.apr__card-head {
  grid-area: head;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 12px;
}
.apr__card-check {
  padding: 6px;
  margin: -6px;
}
.apr__card-lock {
  color: var(--color-text-subtle);
}
.apr__card-title {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px 10px;
  min-width: 0;
}
.apr__card-number {
  font-size: 15px;
  letter-spacing: 0.01em;
}
.apr__card-date {
  font-size: 12.5px;
  color: var(--color-text-subtle);
  white-space: nowrap;
}
/* Тип заказа — иконкой (полное название в title/aria-label). */
.apr__card-type {
  display: inline-flex;
  align-items: center;
}
.apr__card-type--supplier {
  color: var(--color-warning);
}
.apr__card-type--internal {
  color: var(--color-info);
}
.apr__card-actions {
  grid-area: actions;
  display: flex;
  align-items: center;
  gap: 8px;
}

/* Реквизиты: выровненная сетка, метка над значением.
   4 колонки на широких, 2 на средних, строки «метка: значение» на мобильных. */
.apr__props {
  grid-area: props;
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(0, 1.5fr) minmax(0, 1.2fr) minmax(0, 0.9fr);
  gap: 12px 24px;
  margin: 12px 0 2px;
}
.apr__prop {
  min-width: 0;
}
.apr__prop dt {
  margin-bottom: 2px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--color-text-subtle);
}
.apr__prop dd {
  margin: 0;
  font-size: 13.5px;
  font-weight: 500;
  color: var(--color-text);
  overflow-wrap: break-word;
}
.apr__prop-amount {
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.apr__prop--project {
  grid-column: 1 / -1;
}

@media (max-width: 1023px) {
  .apr__props {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

/* Мобильный (основная платформа согласующих): одна колонка —
   шапка «чекбокс + номер + дата + иконка типа» в одну строку,
   реквизиты текстовым потоком «метка: значение» (перенос внутри
   значения, как в старом PHP), большие кнопки внизу. */
@media (max-width: 639px) {
  .apr {
    /* Боковые отступы страницы сжимаем — иначе карточка тесная. */
    --page-gutter: 10px;
  }
  .apr__card :deep(.n-card-content) {
    padding: 12px 10px;
  }
  .apr__card-grid {
    grid-template-columns: minmax(0, 1fr);
    grid-template-areas:
      'head'
      'props'
      'actions';
  }
  .apr__card-head {
    flex-wrap: nowrap;
    gap: 8px;
  }
  .apr__card-check {
    padding: 4px;
    margin: -4px;
  }
  .apr__card-title {
    gap: 4px 8px;
  }
  .apr__card-number {
    font-size: 16px;
    white-space: nowrap;
  }
  .apr__card-type {
    margin-left: auto;
  }
  .apr__card-date {
    font-size: 13px;
  }
  .apr__props {
    display: block;
    margin: 10px 0 0;
  }
  .apr__prop {
    padding: 4px 0;
  }
  .apr__prop dt {
    display: inline;
    margin: 0;
    font-size: 15px;
    font-weight: 400;
    text-transform: none;
    letter-spacing: normal;
    color: var(--color-text-muted);
  }
  .apr__prop dt::after {
    content: ':';
  }
  .apr__prop dd {
    display: inline;
    margin-left: 4px;
    font-size: 15px;
  }
  .apr__card-actions {
    margin-top: 12px;
  }
  .apr__card-actions :deep(.n-button) {
    flex: 1;
    height: 40px;
    font-size: 15px;
  }
}
</style>
