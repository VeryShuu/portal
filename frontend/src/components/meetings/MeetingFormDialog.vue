<template>
  <n-modal
    :show="show"
    :title="isEdit ? t('meetings.form.editTitle') : t('meetings.form.createTitle')"
    preset="card"
    style="max-width: 560px; width: 100%; max-height: 90vh; overflow-y: auto"
    :mask-closable="false"
    @update:show="$emit('update:show', $event)"
  >
    <n-form
      ref="formRef"
      :model="form"
      label-placement="top"
      require-mark-placement="right-hanging"
    >
      <MeetingFormFields
        v-model:form="form"
        :rooms="rooms"
        :rooms-loading="roomsLoading"
        :date-locale-value="dateLocaleValue"
        :duration-options="durationOptions"
        :selected-duration="selectedDuration"
        @update:selected-duration="selectedDuration = $event"
        @toggle-room="toggleRoom"
      />

      <MeetingFormParticipants
        v-model:form="form"
        :min-search-chars="minSearchChars"
      />

      <MeetingFormRecurrence
        v-model:form="form"
        :is-edit="isEdit"
        :has-series="!!booking?.series_id"
        :start-date-str="startDateStr"
        :max-recurrence-days="maxRecurrenceDays"
      />
    </n-form>

    <div
      v-if="conflictError"
      class="conflict-error"
    >
      <strong>{{ t('meetings.conflict.title') }}</strong>
      <ul>
        <li
          v-for="(c, i) in conflictError"
          :key="i"
        >
          {{ c.room_name }}: {{ c.booking_title }} ({{ formatConflictTime(c.start, c.end) }})
        </li>
      </ul>
    </div>

    <template #footer>
      <n-space justify="end">
        <n-button @click="$emit('update:show', false)">
          {{ t('common.cancel') }}
        </n-button>
        <n-button
          v-if="isEdit && canDelete"
          type="error"
          ghost
          :loading="deleting"
          @click="onDelete"
        >
          {{ t('common.delete') }}
        </n-button>
        <n-button
          type="primary"
          :loading="saving"
          @click="onSubmit"
        >
          {{ t('common.save') }}
        </n-button>
      </n-space>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NModal, NForm, NButton, NSpace } from 'naive-ui'
import type { BookingOut } from '../../api/meetings'
import MeetingFormFields from './meeting-form/MeetingFormFields.vue'
import MeetingFormParticipants from './meeting-form/MeetingFormParticipants.vue'
import MeetingFormRecurrence from './meeting-form/MeetingFormRecurrence.vue'
import { useMeetingFormState } from './meeting-form/composables/useMeetingFormState'

const props = defineProps<{
  show: boolean
  booking?: BookingOut | null
  prefillRoomIds?: string[]
  prefillStart?: string
  prefillEnd?: string
}>()

const emit = defineEmits<{
  (e: 'update:show', v: boolean): void
  (e: 'saved'): void
}>()

const { t } = useI18n()

const {
  form,
  formRef,
  saving,
  deleting,
  conflictError,
  selectedDuration,
  durationOptions,
  startDateStr,
  isEdit,
  canDelete,
  minSearchChars,
  maxRecurrenceDays,
  dateLocaleValue,
  rooms,
  roomsLoading,
  toggleRoom,
  onSubmit,
  onDelete,
  formatConflictTime,
} = useMeetingFormState(props, emit)
</script>

<style scoped>
.conflict-error {
  background: #fff1f0;
  border: 1px solid #ffa39e;
  border-radius: 4px;
  padding: 10px 14px;
  font-size: 13px;
  color: #c0392b;
  margin-top: 12px;
}
.conflict-error ul {
  margin: 6px 0 0 16px;
  padding: 0;
}
.conflict-error li {
  margin: 2px 0;
}
</style>
