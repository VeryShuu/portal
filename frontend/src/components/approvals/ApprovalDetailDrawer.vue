<template>
  <n-drawer
    :show="show"
    :width="'min(640px, 100vw)'"
    placement="right"
    @update:show="$emit('close')"
  >
    <n-drawer-content
      :title="drawerTitle"
      closable
    >
      <n-spin
        v-if="loading"
        class="apr-detail__spin"
      />
      <!-- Ошибка загрузки ≠ вечный спиннер: явный error-state с повтором
           (ревью 2026-09-05 — detailLoading считался по отсутствию данных). -->
      <n-alert
        v-else-if="error"
        type="error"
        :show-icon="true"
      >
        {{ t('approvals.detailError') }}
        <n-button
          size="small"
          style="margin-left: 12px"
          @click="$emit('retry')"
        >
          {{ t('approvals.retry') }}
        </n-button>
      </n-alert>
      <template v-else-if="doc">
        <!-- Реквизиты -->
        <div class="apr-detail__head">
          <n-tag
            size="small"
            :type="doc.has_prices ? 'warning' : 'info'"
          >
            {{ typeLabel }}
          </n-tag>
          <span class="apr-detail__date">{{ doc.date }}</span>
        </div>

        <dl class="apr-detail__props">
          <div class="apr-detail__row">
            <dt>{{ t('approvals.props.organization') }}</dt>
            <dd>{{ doc.organization }}</dd>
          </div>
          <div class="apr-detail__row">
            <dt>{{ doc.has_prices ? t('approvals.props.manager') : t('approvals.props.responsible') }}</dt>
            <dd>{{ doc.manager || '—' }}</dd>
          </div>
          <div
            v-if="doc.has_prices"
            class="apr-detail__row"
          >
            <dt>{{ t('approvals.props.contractor') }}</dt>
            <dd>{{ doc.contractor || '—' }}</dd>
          </div>
          <div
            v-if="doc.has_prices"
            class="apr-detail__row"
          >
            <dt>{{ t('approvals.props.project') }}</dt>
            <dd>{{ doc.project || '—' }}</dd>
          </div>
          <div
            v-if="!doc.has_prices"
            class="apr-detail__row"
          >
            <dt>{{ t('approvals.props.activity') }}</dt>
            <dd>{{ doc.activity_direction || '—' }}</dd>
          </div>
          <div
            v-if="!doc.has_prices && headerRecipient"
            class="apr-detail__row"
          >
            <dt>{{ t('approvals.props.department') }}</dt>
            <dd>{{ headerRecipient }}</dd>
          </div>
          <div
            v-if="doc.has_prices && doc.amount != null"
            class="apr-detail__row"
          >
            <dt>{{ t('approvals.props.amount') }}</dt>
            <dd class="apr-detail__amount">
              {{ formatAmount(doc.amount, locale) }} {{ doc.currency }}
            </dd>
          </div>
          <div
            v-if="doc.sed_url"
            class="apr-detail__row"
          >
            <dt>{{ t('approvals.props.sed') }}</dt>
            <dd>
              <a
                :href="doc.sed_url"
                target="_blank"
                rel="noopener"
              >{{ t('approvals.props.sedLink') }}</a>
            </dd>
          </div>
          <div
            v-if="doc.comment"
            class="apr-detail__row"
          >
            <dt>{{ t('approvals.props.comment') }}</dt>
            <dd>{{ doc.comment }}</dd>
          </div>
        </dl>

        <!-- История согласования -->
        <n-collapse v-if="(doc.history ?? []).length > 0">
          <n-collapse-item
            :title="t('approvals.history.title')"
            name="history"
          >
            <ol class="apr-timeline">
              <li
                v-for="(item, i) in doc.history ?? []"
                :key="i"
                class="apr-timeline__item"
                :class="{ 'apr-timeline__item--active': i === (doc.history ?? []).length - 1 }"
              >
                <div class="apr-timeline__period">
                  {{ item.period }}
                </div>
                <div>{{ item.user }}</div>
                <div class="apr-timeline__event">
                  {{ item.event }}
                </div>
                <div
                  v-if="item.comment"
                  class="apr-timeline__comment"
                >
                  {{ item.comment }}
                </div>
              </li>
            </ol>
          </n-collapse-item>
        </n-collapse>

        <!-- Товары -->
        <h4 class="apr-detail__subtitle">
          {{ t('approvals.products.title') }}
        </h4>
        <div class="apr-detail__table-wrap">
          <n-table
            size="small"
            :single-line="false"
          >
            <thead>
              <tr>
                <th>{{ t('approvals.products.name') }}</th>
                <th v-if="doc.has_prices">
                  {{ t('approvals.products.recipient') }}
                </th>
                <th class="apr-detail__num">
                  {{ t('approvals.products.quantity') }}
                </th>
                <th
                  v-if="doc.has_prices"
                  class="apr-detail__num"
                >
                  {{ t('approvals.products.price') }}
                </th>
                <th
                  v-if="doc.has_prices"
                  class="apr-detail__num"
                >
                  {{ t('approvals.products.total') }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(item, i) in doc.products ?? []"
                :key="i"
              >
                <td>{{ item.name }}</td>
                <td v-if="doc.has_prices">
                  {{ item.recipient || '—' }}
                </td>
                <td class="apr-detail__num">
                  {{ item.quantity }}
                </td>
                <template v-if="doc.has_prices">
                  <td class="apr-detail__num">
                    <span class="apr-detail__nowrap">{{ item.price == null ? '—' : formatAmount(item.price, locale) }} {{ doc.currency }}</span>
                  </td>
                  <td class="apr-detail__num">
                    <span class="apr-detail__nowrap">{{ item.total == null ? '—' : formatAmount(item.total, locale) }} {{ doc.currency }}</span>
                  </td>
                </template>
              </tr>
            </tbody>
          </n-table>
        </div>

        <!-- Вложения -->
        <template v-if="(doc.attachments ?? []).length > 0">
          <h4 class="apr-detail__subtitle">
            {{ t('approvals.attachments.title') }}
          </h4>
          <ul class="apr-detail__files">
            <li
              v-for="att in doc.attachments ?? []"
              :key="att.index"
            >
              <a
                :href="approvalAttachmentUrl(doc.guid, att.index)"
                target="_blank"
                rel="noopener"
              >{{ att.name }}</a>
            </li>
          </ul>
        </template>

        <!-- Действия (v2.1.0.0: внутренние заказы согласуются в общем
             потоке — 1С запишет Employee ответственным и завершит этап) -->
        <div class="apr-detail__actions">
          <n-form-item
            :label="t('approvals.actions.comment')"
            label-placement="top"
          >
            <n-input
              v-model:value="comment"
              type="textarea"
              :placeholder="t('approvals.actions.commentPlaceholder')"
              :autosize="{ minRows: 3, maxRows: 6 }"
            />
          </n-form-item>

          <n-form-item
            v-if="doc.requires_manager"
            :label="t('approvals.actions.selectManager')"
            label-placement="top"
          >
            <n-select
              v-model:value="managerGuid"
              :options="managerOptions"
              :placeholder="t('approvals.actions.selectManagerPlaceholder')"
              clearable
            />
          </n-form-item>

          <div class="apr-detail__buttons">
            <n-button
              type="error"
              ghost
              :disabled="!comment.trim()"
              :loading="running"
              @click="$emit('reject')"
            >
              {{ t('approvals.actions.reject') }}
            </n-button>
            <n-button
              type="success"
              :disabled="doc.requires_manager && !managerGuid"
              :loading="running"
              @click="$emit('approve')"
            >
              {{ t('approvals.actions.approve') }}
            </n-button>
          </div>
          <p
            v-if="doc.requires_manager"
            class="apr-detail__hint"
          >
            {{ t('approvals.actions.managerRequiredHint') }}
          </p>
        </div>
      </template>
    </n-drawer-content>
  </n-drawer>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NAlert,
  NButton,
  NCollapse,
  NCollapseItem,
  NDrawer,
  NDrawerContent,
  NFormItem,
  NInput,
  NSelect,
  NSpin,
  NTable,
  NTag,
} from 'naive-ui'
import { approvalAttachmentUrl } from '../../api/approvals'
import { formatAmount } from '../../utils/formatAmount'

const props = defineProps<{
  show: boolean
  loading: boolean
  error: boolean
  running: boolean
  doc: import('../../api/approvals').ApprovalDocumentDetail | null
  comment: string
  managerGuid: string | null
}>()

const emit = defineEmits<{
  close: []
  approve: []
  reject: []
  retry: []
  'update:comment': [value: string]
  'update:managerGuid': [value: string | null]
}>()

const { t, locale } = useI18n()

const comment = computed({
  get: () => props.comment,
  set: (v: string) => emit('update:comment', v),
})
const managerGuid = computed({
  get: () => props.managerGuid,
  set: (v: string | null) => emit('update:managerGuid', v),
})

const drawerTitle = computed(() =>
  props.doc ? `${props.doc.number} ${props.doc.date}` : t('approvals.detailTitle'),
)

const typeLabel = computed(() =>
  props.doc?.has_prices ? t('approvals.types.supplier') : t('approvals.types.internal'),
)

const managerOptions = computed(() =>
  (props.doc?.managers ?? []).map((m) => ({ label: m.name, value: m.guid })),
)

/** Шапочное подразделение внутреннего заказа (v2.1.0.0): «Получатель»
 * одинаков во всех строках — берём первую. */
const headerRecipient = computed(
  () => props.doc?.products?.[0]?.recipient?.trim() || '',
)
</script>

<style scoped>
.apr-detail__spin {
  display: block;
  margin: 48px auto;
}
.apr-detail__head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}
.apr-detail__date {
  font-size: 12px;
  color: var(--color-text-subtle);
}
.apr-detail__props {
  margin: 0 0 16px;
}
.apr-detail__row {
  display: flex;
  gap: 12px;
  padding: 4px 0;
  font-size: 13px;
}
.apr-detail__row dt {
  flex-shrink: 0;
  width: 180px;
  color: var(--color-text-muted);
}
.apr-detail__row dd {
  margin: 0;
  min-width: 0;
  overflow-wrap: anywhere;
}
.apr-detail__amount {
  font-weight: 700;
}
.apr-detail__subtitle {
  margin: 16px 0 8px;
  font-size: 14px;
  font-weight: 700;
}
.apr-detail__table-wrap {
  overflow-x: auto;
}
.apr-detail__num {
  text-align: right;
  white-space: nowrap;
}
.apr-detail__nowrap {
  white-space: nowrap;
}
.apr-detail__files {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  line-height: 1.8;
}
.apr-detail__actions {
  margin-top: 20px;
}
.apr-detail__buttons {
  display: flex;
  justify-content: space-between;
  margin-top: 4px;
}
.apr-detail__hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--color-text-subtle);
}
.apr-timeline {
  position: relative;
  margin: 0;
  padding-left: 20px;
  list-style: none;
}
.apr-timeline::before {
  content: '';
  position: absolute;
  left: 6px;
  top: 4px;
  bottom: 4px;
  width: 2px;
  background: var(--color-border);
}
.apr-timeline__item {
  position: relative;
  padding: 0 0 14px 8px;
  font-size: 13px;
}
.apr-timeline__item::before {
  content: '';
  position: absolute;
  left: -18px;
  top: 4px;
  width: 10px;
  height: 10px;
  border: 2px solid var(--color-border-strong, #ccc);
  border-radius: 50%;
  background: var(--color-surface);
}
.apr-timeline__item--active::before {
  border-color: var(--color-success);
  background: var(--color-success);
}
.apr-timeline__period {
  font-weight: 700;
}
.apr-timeline__event {
  color: var(--color-text-muted);
}
.apr-timeline__comment {
  font-style: italic;
}

/* Мобильный (основная платформа согласующих): реквизиты строками
  «метка: значение», крупные кнопки действий. */
@media (max-width: 639px) {
  .apr-detail__row {
    flex-wrap: wrap;
    gap: 2px 6px;
    padding: 5px 0;
    font-size: 15px;
  }
  .apr-detail__row dt {
    width: auto;
    color: var(--color-text-muted);
  }
  .apr-detail__row dt::after {
    content: ':';
  }
  .apr-detail__files {
    font-size: 14px;
  }
  .apr-detail__buttons {
    gap: 12px;
  }
  .apr-detail__buttons :deep(.n-button) {
    flex: 1;
    height: 40px;
    font-size: 15px;
  }
}
</style>
