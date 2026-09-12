<template>
  <div class="recurrence-editor">
    <n-checkbox
      :checked="enabled"
      @update:checked="onToggle"
    >
      {{ t('meetings.recurrence.repeat') }}
    </n-checkbox>

    <template v-if="enabled && modelValue">
      <n-form-item :label="t('meetings.recurrence.freq')">
        <n-select
          :value="modelValue.freq"
          :options="freqOptions"
          @update:value="onFreqChange"
        />
      </n-form-item>

      <n-form-item :label="t('meetings.recurrence.until')">
        <n-date-picker
          :value="untilTimestamp"
          type="date"
          :is-date-disabled="isDateDisabled"
          @update:value="onUntilChange"
        />
      </n-form-item>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NCheckbox, NFormItem, NSelect, NDatePicker } from 'naive-ui'
import type { RecurrenceRule } from '../../api/meetings'

const props = defineProps<{
  modelValue: RecurrenceRule | null
  startDate: string
  maxDays?: number
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: RecurrenceRule | null): void
}>()

const { t } = useI18n()

const maxDays = computed(() => props.maxDays ?? 31)
const enabled = computed(() => props.modelValue !== null)

const freqOptions = computed(() => [
  { label: t('meetings.recurrence.daily'), value: 'DAILY' },
  { label: t('meetings.recurrence.weekdays'), value: 'WEEKDAYS' },
  { label: t('meetings.recurrence.weekly'), value: 'WEEKLY' },
  { label: t('meetings.recurrence.biweekly'), value: 'BIWEEKLY' },
  { label: t('meetings.recurrence.monthly'), value: 'MONTHLY' },
])

function parseYmd(s: string): Date {
  const [y, m, d] = s.split('-').map(Number)
  return new Date(y, (m ?? 1) - 1, d ?? 1)
}

function toYmd(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function defaultUntil(): string {
  const d = parseYmd(props.startDate)
  d.setDate(d.getDate() + 6)
  return toYmd(d)
}

function onToggle(checked: boolean) {
  if (checked) {
    emit('update:modelValue', { freq: 'WEEKLY', until_date: defaultUntil() })
  } else {
    emit('update:modelValue', null)
  }
}

function onFreqChange(freq: RecurrenceRule['freq']) {
  if (!props.modelValue) return
  emit('update:modelValue', { ...props.modelValue, freq })
}

const untilTimestamp = computed(() => {
  if (!props.modelValue) return null
  return parseYmd(props.modelValue.until_date).getTime()
})

function onUntilChange(ts: number | null) {
  if (!props.modelValue || ts === null) return
  const d = new Date(ts)
  const localDay = new Date(d.getFullYear(), d.getMonth(), d.getDate())
  emit('update:modelValue', { ...props.modelValue, until_date: toYmd(localDay) })
}

function isDateDisabled(ts: number): boolean {
  const start = parseYmd(props.startDate)
  start.setHours(0, 0, 0, 0)
  const max = parseYmd(props.startDate)
  max.setDate(max.getDate() + maxDays.value)
  max.setHours(0, 0, 0, 0)
  const d = new Date(ts)
  const day = new Date(d.getFullYear(), d.getMonth(), d.getDate())
  return day <= start || day > max
}
</script>

<style scoped>
.recurrence-editor {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
</style>
