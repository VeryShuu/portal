<template>
  <n-alert
    :type="failed > 0 ? 'warning' : 'success'"
    :show-icon="true"
    closable
    class="apr-report"
    @close="$emit('dismiss')"
  >
    <div class="apr-report__head">
      <strong>{{ t('approvals.bulkReport.title') }}</strong>
      <span class="apr-report__counts">
        {{ t('approvals.bulkReport.approved', { n: approved }) }}
        <template v-if="failed > 0">
          ·
          <span class="apr-report__failed">{{ t('approvals.bulkReport.failed', { n: failed }) }}</span>
        </template>
      </span>
    </div>
    <ul class="apr-report__rows">
      <li
        v-for="row in rows"
        :key="row.uuid"
        class="apr-report__row"
        :class="{ 'apr-report__row--ok': row.ok }"
      >
        <n-icon
          size="14"
          :color="row.ok ? 'var(--color-success, #18a058)' : 'var(--color-error, #d03050)'"
        >
          <CheckmarkCircleOutline v-if="row.ok" />
          <CloseCircleOutline v-else />
        </n-icon>
        <span class="apr-report__doc">
          <strong>{{ row.label }}</strong>
          <span
            v-if="row.sub"
            class="apr-report__sub"
          >
            {{ row.sub }}
          </span>
        </span>
        <span class="apr-report__message">{{ row.message }}</span>
      </li>
    </ul>
  </n-alert>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NAlert, NIcon } from 'naive-ui'
import { CheckmarkCircleOutline, CloseCircleOutline } from '@vicons/ionicons5'
import type { BulkApproveReportRow } from '../../pages/composables/useApprovalsPage'

defineProps<{
  approved: number
  failed: number
  rows: BulkApproveReportRow[]
}>()

defineEmits<{ dismiss: [] }>()

const { t } = useI18n()
</script>

<style scoped>
.apr-report {
  margin-bottom: 12px;
}
.apr-report__head {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 6px;
}
.apr-report__counts {
  font-size: 13px;
}
.apr-report__failed {
  font-weight: 700;
}
.apr-report__rows {
  margin: 0;
  padding: 0;
  list-style: none;
  max-height: 260px;
  overflow-y: auto;
}
.apr-report__row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 3px 0;
  font-size: 13px;
}
.apr-report__doc {
  display: flex;
  gap: 8px;
  min-width: 0;
  flex-shrink: 0;
}
.apr-report__sub {
  color: var(--color-text-secondary, #888);
}
.apr-report__message {
  color: var(--color-text-secondary, #666);
  overflow-wrap: anywhere;
}
</style>
