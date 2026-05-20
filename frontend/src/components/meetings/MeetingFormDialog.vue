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
              v-model:value="selectedDuration"
              :options="durationOptions"
              :placeholder="t('meetings.form.durationCustom')"
              clearable
              style="width: 100%"
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
            @click="toggleRoom(room.id)"
          >
            {{ room.name }}
          </button>
        </div>
      </n-form-item>

      <n-form-item :label="t('meetings.form.participants')">
        <ParticipantPicker
          v-model="form.invited_users"
          :min-chars="minSearchChars"
        />
      </n-form-item>

      <n-form-item
        v-if="!isEdit"
        :label="t('meetings.form.recurrence')"
      >
        <RecurrenceEditor
          v-model="form.recurrence"
          :start-date="startDateStr"
          :max-days="maxRecurrenceDays"
        />
      </n-form-item>

      <template v-if="isEdit && booking?.series_id">
        <n-form-item :label="t('meetings.form.applyTo')">
          <n-radio-group v-model:value="form.apply_to">
            <n-space>
              <n-radio value="this">
                {{ t('meetings.form.applyToThis') }}
              </n-radio>
              <n-radio value="series">
                {{ t('meetings.form.applyToSeries') }}
              </n-radio>
            </n-space>
          </n-radio-group>
        </n-form-item>
      </template>
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
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NModal, NForm, NFormItem, NInput, NSpin, NButton, NSpace,
  NGrid, NGi, NDatePicker, NRadioGroup, NRadio, NSelect,
  dateRuRU, dateEnUS,
  useMessage,
  type FormInst,
} from 'naive-ui'
import { mapMeetingsError } from '../../utils/mapMeetingsError'
import { useModulesStore } from '../../stores/modules'
import { useAuthStore } from '../../stores/auth'
import {
  useMeetingRoomsQuery,
  useCreateBookingMutation,
  useUpdateBookingMutation,
  useDeleteBookingMutation,
  useUpdateSeriesMutation,
  useDeleteSeriesMutation,
} from '../../queries/meetings'
import type { BookingOut, InvitedUser, RecurrenceRule } from '../../api/meetings'
import ParticipantPicker from './ParticipantPicker.vue'
import RecurrenceEditor from './RecurrenceEditor.vue'

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

const { t, locale } = useI18n()
const message = useMessage()
const modulesStore = useModulesStore()
const auth = useAuthStore()

const isEdit = computed(() => !!props.booking)
const canDelete = computed(() =>
  !!props.booking && (
    props.booking.creator_id === auth.user?.id || auth.isAdmin
  ),
)

const minSearchChars = computed(() => modulesStore.meetingsSettings.min_search_chars)
const maxRecurrenceDays = computed(() => modulesStore.meetingsSettings.max_recurrence_horizon_days)
const modulesEnabled = computed(() => modulesStore.isEnabled('meetings'))
const dateLocaleValue = computed(() => (locale.value === 'ru' ? dateRuRU : dateEnUS))

const { data: rooms, isLoading: roomsLoading } = useMeetingRoomsQuery(false, { enabled: modulesEnabled })

function toggleRoom(id: string) {
  const idx = form.value.room_ids.indexOf(id)
  if (idx === -1) {
    form.value.room_ids = [...form.value.room_ids, id]
  } else {
    form.value.room_ids = form.value.room_ids.filter(r => r !== id)
  }
}

interface FormState {
  title: string
  description: string
  room_ids: string[]
  invited_users: InvitedUser[]
  recurrence: RecurrenceRule | null
  apply_to: 'this' | 'series'
  start_time: number | null
  end_time: number | null
}

function toTimestamp(iso: string | undefined): number | null {
  return iso ? new Date(iso).getTime() : null
}

function makeForm(): FormState {
  if (props.booking) {
    return {
      title: props.booking.title,
      description: props.booking.description ?? '',
      room_ids: props.booking.rooms.map(r => r.id),
      invited_users: [...props.booking.invited_users],
      recurrence: null,
      apply_to: 'this',
      start_time: toTimestamp(props.booking.start_time),
      end_time: toTimestamp(props.booking.end_time),
    }
  }
  return {
    title: '',
    description: '',
    room_ids: props.prefillRoomIds ?? [],
    invited_users: [],
    recurrence: null,
    apply_to: 'this',
    start_time: toTimestamp(props.prefillStart),
    end_time: toTimestamp(props.prefillEnd),
  }
}

const DURATION_PRESETS = [30, 60, 90, 120, 150, 180]
const MS_PER_MIN = 60_000

function getInitialDuration(): number | null {
  if (props.booking) {
    const diffMin = Math.round(
      (new Date(props.booking.end_time).getTime() - new Date(props.booking.start_time).getTime()) / MS_PER_MIN,
    )
    return DURATION_PRESETS.includes(diffMin) ? diffMin : null
  }
  return 60
}

const form = ref<FormState>(makeForm())
const formRef = ref<FormInst | null>(null)
const saving = ref(false)
const deleting = ref(false)
const conflictError = ref<Array<{ room_name: string; booking_title: string; start: string; end: string }> | null>(null)
const selectedDuration = ref<number | null>(getInitialDuration())

const durationOptions = computed(() => [
  { label: t('meetings.form.duration30'),  value: 30 },
  { label: t('meetings.form.duration60'),  value: 60 },
  { label: t('meetings.form.duration90'),  value: 90 },
  { label: t('meetings.form.duration120'), value: 120 },
  { label: t('meetings.form.duration150'), value: 150 },
  { label: t('meetings.form.duration180'), value: 180 },
])

const startDateStr = computed(() => {
  if (!form.value.start_time) return new Date().toISOString().slice(0, 10)
  return new Date(form.value.start_time).toISOString().slice(0, 10)
})

watch(selectedDuration, (dur) => {
  if (dur !== null && form.value.start_time !== null) {
    form.value.end_time = form.value.start_time + dur * MS_PER_MIN
  }
})

watch(() => form.value.start_time, (st) => {
  if (selectedDuration.value !== null && st !== null) {
    form.value.end_time = st + selectedDuration.value * MS_PER_MIN
  }
})

watch(() => props.show, (v) => {
  if (v) {
    form.value = makeForm()
    conflictError.value = null
    selectedDuration.value = getInitialDuration()
  }
})

const { mutateAsync: doCreate } = useCreateBookingMutation()
const { mutateAsync: doUpdate } = useUpdateBookingMutation()
const { mutateAsync: doDelete } = useDeleteBookingMutation()
const { mutateAsync: doUpdateSeries } = useUpdateSeriesMutation()
const { mutateAsync: doDeleteSeries } = useDeleteSeriesMutation()

function tsToIso(ts: number | null): string {
  if (ts === null) return ''
  const d = new Date(ts)
  d.setSeconds(0, 0)
  return d.toISOString()
}

async function onSubmit() {
  conflictError.value = null
  try {
    await formRef.value?.validate()
  } catch {
    return
  }

  saving.value = true
  try {
    if (isEdit.value && props.booking) {
      if (form.value.apply_to === 'series' && props.booking.series_id) {
        await doUpdateSeries({
          seriesId: props.booking.series_id,
          dto: {
            title: form.value.title,
            description: form.value.description || null,
            invited_users: form.value.invited_users,
          },
        })
      } else {
        await doUpdate({
          id: props.booking.id,
          dto: {
            apply_to: form.value.apply_to,
            title: form.value.title,
            description: form.value.description || null,
            start_time: tsToIso(form.value.start_time),
            end_time: tsToIso(form.value.end_time),
            room_ids: form.value.room_ids,
            invited_users: form.value.invited_users,
          },
        })
      }
    } else {
      await doCreate({
        title: form.value.title,
        description: form.value.description || null,
        start_time: tsToIso(form.value.start_time),
        end_time: tsToIso(form.value.end_time),
        room_ids: form.value.room_ids,
        invited_users: form.value.invited_users,
        recurrence: form.value.recurrence,
      })
    }
    message.success(t('meetings.form.savedSuccess'))
    emit('update:show', false)
    emit('saved')
  } catch (err: unknown) {
    const code = mapMeetingsError(err)
    if (code === 'BOOKING_CONFLICT') {
      const e = err as { data?: { conflicts?: unknown[] } }
      conflictError.value = e.data?.conflicts as Array<{ room_name: string; booking_title: string; start: string; end: string }>
    } else if (code === 'START_TIME_IN_PAST') {
      message.error(t('meetings.form.startTimeInPast'), { duration: 5000 })
    } else if (code === 'END_BEFORE_START') {
      message.error(t('meetings.form.endTimeAfterStart'), { duration: 5000 })
    } else {
      message.error(t('meetings.form.saveError'))
    }
  } finally {
    saving.value = false
  }
}

async function onDelete() {
  if (!props.booking) return
  deleting.value = true
  try {
    if (form.value.apply_to === 'series' && props.booking.series_id) {
      await doDeleteSeries(props.booking.series_id)
    } else {
      await doDelete({ id: props.booking.id, dto: { apply_to: 'this' } })
    }
    message.success(t('meetings.form.deletedSuccess'))
    emit('update:show', false)
    emit('saved')
  } catch {
    message.error(t('meetings.form.deleteError'))
  } finally {
    deleting.value = false
  }
}

function formatConflictTime(start: string, end: string): string {
  const s = new Date(start)
  const e = new Date(end)
  const loc = locale.value === 'ru' ? 'ru-RU' : 'en-GB'
  return `${s.toLocaleTimeString(loc, { hour: '2-digit', minute: '2-digit' })}–${e.toLocaleTimeString(loc, { hour: '2-digit', minute: '2-digit' })}`
}
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
