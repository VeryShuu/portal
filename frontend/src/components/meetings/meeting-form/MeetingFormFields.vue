<template>
  <n-form-item
    :label="t('meetings.form.title')"
    path="title"
    :rule="{ required: true, message: t('meetings.form.titleRequired') }"
  >
    <n-input
      v-model:value="form.title"
      :placeholder="t('meetings.form.titlePlaceholder')"
      maxlength="500"
    />
  </n-form-item>

  <n-form-item :label="t('meetings.form.description')">
    <n-input
      v-model:value="form.description"
      type="textarea"
      :rows="2"
      :placeholder="t('meetings.form.descriptionPlaceholder')"
    />
  </n-form-item>

  <n-grid
    :cols="2"
    :x-gap="12"
  >
    <n-gi>
      <n-form-item
        :label="t('meetings.form.startTime')"
        path="start_time"
        :rule="{ required: true, message: t('meetings.form.startTimeRequired') }"
      >
        <n-date-picker
          v-model:value="form.start_time"
          type="datetime"
          :time-picker-props="{ minutes: [0,5,10,15,20,25,30,35,40,45,50,55] }"
          :date-locale="dateLocaleValue"
          style="width: 100%"
        />
      </n-form-item>
    </n-gi>
    <n-gi>
      <n-form-item :label="t('meetings.form.duration')">
        <n-select
          :value="selectedDuration"
          :options="durationOptions"
          :placeholder="t('meetings.form.durationCustom')"
          clearable
          style="width: 100%"
          @update:value="emit('update:selectedDuration', $event)"
        />
      </n-form-item>
    </n-gi>
  </n-grid>

  <n-form-item
    :label="t('meetings.form.endTime')"
    path="end_time"
    :rule="[
      { required: true, message: t('meetings.form.endTimeRequired') },
      {
        validator: (_rule: unknown, value: number | null) =>
          !value || !form.start_time || value > form.start_time
            ? true
            : new Error(t('meetings.form.endTimeAfterStart')),
        trigger: ['change', 'blur'],
      },
    ]"
  >
    <n-date-picker
      v-model:value="form.end_time"
      type="datetime"
      :time-picker-props="{ minutes: [0,5,10,15,20,25,30,35,40,45,50,55] }"
      :date-locale="dateLocaleValue"
      style="width: 100%"
    />
  </n-form-item>

  <n-form-item
    :label="t('meetings.form.rooms')"
    path="room_ids"
    :rule="{ required: true, type: 'array', min: 1, message: t('meetings.form.roomsRequired') }"
  >
    <div
      v-if="roomsLoading"
      class="room-chips"
    >
      <n-spin size="small" />
    </div>
    <div
      v-else
      class="room-chips"
    >
      <button
        v-for="room in (rooms ?? [])"
        :key="room.id"
        type="button"
        class="room-chip"
        :class="{ 'room-chip--selected': form.room_ids.includes(room.id) }"
        @click="emit('toggle-room', room.id)"
      >
        {{ room.name }}
      </button>
    </div>
  </n-form-item>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import {
  NFormItem, NInput, NSpin, NGrid, NGi, NDatePicker, NSelect,
} from 'naive-ui'
import type { FormState } from './composables/useMeetingFormState'

defineProps<{
  form: FormState
  rooms: Array<{ id: string; name: string }> | undefined
  roomsLoading: boolean
  dateLocaleValue: object
  durationOptions: Array<{ label: string; value: number }>
  selectedDuration: number | null
}>()

const emit = defineEmits<{
  'update:selectedDuration': [val: number | null]
  'toggle-room': [id: string]
}>()

const { t } = useI18n()
</script>

<style scoped>
.room-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  width: 100%;
  min-height: 32px;
  align-items: center;
}
.room-chip {
  padding: 4px 14px;
  border-radius: 16px;
  border: 1px solid var(--n-border-color, #d9d9d9);
  background: transparent;
  cursor: pointer;
  font-size: 13px;
  color: var(--n-text-color, #333);
  transition: border-color 0.2s, background 0.2s, color 0.2s;
  line-height: 1.6;
  white-space: nowrap;
}
.room-chip:hover {
  border-color: var(--primary-color, #2080f0);
  color: var(--primary-color, #2080f0);
}
.room-chip--selected {
  background: var(--primary-color, #2080f0);
  border-color: var(--primary-color, #2080f0);
  color: #fff;
}
.room-chip--selected:hover {
  color: #fff;
}
</style>
