<template>
  <n-spin :show="isLoading">
    <n-form
      v-if="form"
      label-placement="top"
      :show-feedback="false"
    >
      <div class="kb-grid">
        <n-form-item :label="t('admin.helpdesk.digest.digestHour')">
          <n-input-number
            v-model:value="form.digest_hour"
            :min="0"
            :max="23"
            :show-button="false"
            style="width: 100%"
          />
        </n-form-item>
        <n-form-item :label="t('admin.helpdesk.digest.digestMinute')">
          <n-input-number
            v-model:value="form.digest_minute"
            :min="0"
            :max="59"
            :show-button="false"
            style="width: 100%"
          />
        </n-form-item>
      </div>

      <div class="kb-grid kb-grid--single">
        <n-form-item :label="t('admin.helpdesk.digest.digestSchedule')">
          <n-select
            v-model:value="form.digest_schedule"
            :options="scheduleOptions"
          />
        </n-form-item>
      </div>

      <div class="helpdesk-digest__toggle">
        <n-checkbox v-model:checked="form.enabled">
          {{ t('admin.helpdesk.digest.enabled') }}
        </n-checkbox>
      </div>

      <div class="helpdesk-digest__hint">
        {{ t('admin.helpdesk.digest.hint') }}
      </div>

      <div class="email-actions">
        <n-button
          type="primary"
          :loading="putMut.isPending.value"
          :disabled="!isDirty"
          @click="onSave"
        >
          {{ t('common.save') }}
        </n-button>
      </div>
    </n-form>
  </n-spin>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  useMessage,
  NSpin,
  NForm,
  NFormItem,
  NInputNumber,
  NSelect,
  NCheckbox,
  NButton,
} from 'naive-ui'
import type {
  HelpdeskDigestSchedule,
  HelpdeskDigestSettingsIn,
} from '../../api/helpdesk'
import { useHelpdeskDigestQuery, usePutHelpdeskDigestMutation } from '../../queries/helpdesk'
import { parseApiError } from '../../utils/parseApiError'

const { t } = useI18n()
const message = useMessage()

const { data, isLoading } = useHelpdeskDigestQuery()
const putMut = usePutHelpdeskDigestMutation()

interface DigestFormState {
  enabled: boolean
  digest_hour: number
  digest_minute: number
  digest_schedule: HelpdeskDigestSchedule
}

// Дефолты бэкенда (singleton засевается миграцией 076): enabled=true, 08:00 UTC,
// weekdays. Используется только до первого ответа GET (form=null → n-spin).
const EMPTY: DigestFormState = {
  enabled: true,
  digest_hour: 8,
  digest_minute: 0,
  digest_schedule: 'weekdays',
}

const form = ref<DigestFormState | null>(null)
const isDirty = ref(false)

const scheduleOptions = computed(() => [
  { label: t('admin.helpdesk.digest.scheduleWeekdays'), value: 'weekdays' as const },
  { label: t('admin.helpdesk.digest.scheduleDaily'), value: 'daily' as const },
])

// Заполняем форму из ответа один раз; затем следим за изменениями для dirty.
watch(
  data,
  (d) => {
    if (!d) return
    form.value = {
      enabled: d.enabled,
      digest_hour: d.digest_hour,
      digest_minute: d.digest_minute,
      digest_schedule: d.digest_schedule,
    }
    isDirty.value = false
  },
  { immediate: true },
)

watch(
  form,
  () => {
    if (form.value) isDirty.value = true
  },
  { deep: true },
)

function buildDto(): HelpdeskDigestSettingsIn {
  const f = form.value ?? EMPTY
  // n-input-number может вернуть null при очистке поля — коалесцируем к дефолту,
  // иначе бэкенд вернёт 422 (обязательное поле без значения).
  return {
    enabled: f.enabled,
    digest_hour: f.digest_hour ?? EMPTY.digest_hour,
    digest_minute: f.digest_minute ?? EMPTY.digest_minute,
    digest_schedule: f.digest_schedule,
  }
}

async function onSave() {
  if (!form.value) return
  try {
    await putMut.mutateAsync(buildDto())
    message.success(t('admin.modules.saved'))
    isDirty.value = false
  } catch (e) {
    message.error(parseApiError(e, t))
  }
}
</script>

<style scoped>
.kb-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.kb-grid--single {
  grid-template-columns: 1fr;
}
.helpdesk-digest__toggle {
  margin: 16px 0 8px;
}
.helpdesk-digest__hint {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin-bottom: 12px;
}
.email-actions {
  display: flex;
  gap: 12px;
}
</style>
