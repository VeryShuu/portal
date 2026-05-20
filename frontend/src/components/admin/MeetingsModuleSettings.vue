<template>
  <div class="meetings-module-settings">
    <div
      v-if="!modulesData?.meetings?.enabled"
      class="module-disabled-hint"
    >
      {{ t('admin.modules.meetings.disabledHint') }}
    </div>

    <template v-else>
      <section class="settings-section">
        <h4 class="settings-section__title">
          {{ t('admin.modules.meetings.title') }}
        </h4>
        <div class="branding-fields">
          <div class="email-row-2">
            <n-form-item
              :label="t('admin.modules.meetings.calendarStartHour')"
              style="margin-bottom:0;flex:1"
            >
              <n-input-number
                v-model:value="form.calendar_start_hour"
                :min="0"
                :max="23"
              />
            </n-form-item>
            <n-form-item
              :label="t('admin.modules.meetings.calendarEndHour')"
              style="margin-bottom:0;flex:1"
            >
              <n-input-number
                v-model:value="form.calendar_end_hour"
                :min="1"
                :max="24"
              />
            </n-form-item>
          </div>
          <div class="email-row-2">
            <n-form-item
              :label="t('admin.modules.meetings.maxRecurrenceHorizonDays')"
              style="margin-bottom:0;flex:1"
            >
              <n-input-number
                v-model:value="form.max_recurrence_horizon_days"
                :min="1"
                :max="365"
              />
            </n-form-item>
            <n-form-item
              :label="t('admin.modules.meetings.minSearchChars')"
              style="margin-bottom:0;flex:1"
            >
              <n-input-number
                v-model:value="form.min_search_chars"
                :min="1"
                :max="10"
              />
            </n-form-item>
          </div>
        </div>
        <div class="settings-actions">
          <n-button @click="goToRooms">
            {{ t('admin.modules.meetings.manageRooms') }}
          </n-button>
          <n-button
            type="primary"
            :loading="saving"
            @click="onSave"
          >
            {{ t('common.save') }}
          </n-button>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NFormItem, NInputNumber, useMessage } from 'naive-ui'
import { useQueryClient } from '@tanstack/vue-query'
import { useRouter } from 'vue-router'
import { api } from '../../api'
import { useModulesAdminQuery } from '../../queries/admin'
import { queryKeys } from '../../queries/keys'
import { ROUTES } from '../../router'

const { t } = useI18n()
const message = useMessage()
const qc = useQueryClient()
const router = useRouter()

const { data: modulesData } = useModulesAdminQuery()

const form = reactive({
  calendar_start_hour: 8,
  calendar_end_hour: 19,
  max_recurrence_horizon_days: 31,
  min_search_chars: 3,
})
const saving = ref(false)

watch(modulesData, (data) => {
  if (!data?.meetings) return
  form.calendar_start_hour = data.meetings.calendar_start_hour
  form.calendar_end_hour = data.meetings.calendar_end_hour
  form.max_recurrence_horizon_days = data.meetings.max_recurrence_horizon_days
  form.min_search_chars = data.meetings.min_search_chars
}, { immediate: true })

async function onSave() {
  saving.value = true
  try {
    await api('/admin/modules/meetings', {
      method: 'PUT',
      body: {
        enabled: modulesData.value?.meetings?.enabled ?? true,
        ...form,
      },
    })
    qc.invalidateQueries({ queryKey: queryKeys.admin.modules() })
    message.success(t('admin.modules.saved'))
  } catch {
    message.error(t('errors.generic'))
  } finally {
    saving.value = false
  }
}

function goToRooms() {
  router.push(ROUTES.MEETINGS_ROOMS)
}
</script>

<style scoped>
.meetings-module-settings {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.module-disabled-hint {
  font-size: 13px;
  color: var(--color-text-muted);
  padding: 12px;
  border: 1px dashed var(--n-border-color, #ddd);
  border-radius: 8px;
}
.settings-section {
  border: 1px solid var(--n-border-color, #eaeaea);
  border-radius: 10px;
  padding: 16px;
}
.settings-section__title {
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 600;
}
.branding-fields {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.email-row-2 {
  display: flex;
  gap: 12px;
}
.settings-actions {
  margin-top: 12px;
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}
</style>
