<template>
  <n-modal
    v-model:show="visible"
    preset="card"
    style="max-width: 480px"
    :title="booking?.title ?? ''"
  >
    <template v-if="booking">
      <div class="booking-detail">
        <div class="booking-detail__row">
          <span class="booking-detail__label">{{ t('meetings.detail.time') }}</span>
          <span>{{ formatTime(booking.start_time) }}–{{ formatTime(booking.end_time) }}</span>
        </div>
        <div class="booking-detail__row">
          <span class="booking-detail__label">{{ t('meetings.detail.rooms') }}</span>
          <div class="booking-detail__rooms">
            <n-tag
              v-for="room in booking.rooms"
              :key="room.id"
              size="small"
              :bordered="false"
              :type="room.kind === 'virtual' ? 'info' : 'default'"
            >
              <template #icon>
                <n-icon :component="room.kind === 'virtual' ? VideocamOutline : LocationOutline" />
              </template>
              {{ room.name }}
            </n-tag>
          </div>
        </div>
        <div class="booking-detail__row">
          <span class="booking-detail__label">{{ t('meetings.detail.organizer') }}</span>
          <span>{{ booking.organizer_name }}</span>
        </div>
        <div
          v-if="booking.description"
          class="booking-detail__row"
        >
          <span class="booking-detail__label">{{ t('meetings.detail.description') }}</span>
          <span>{{ booking.description }}</span>
        </div>
        <div
          v-if="booking.invited_users.length"
          class="booking-detail__row"
        >
          <span class="booking-detail__label">
            {{ t('meetings.detail.participants') }}
            <span class="booking-detail__count">({{ booking.invited_users.length }})</span>
          </span>
          <div class="booking-detail__participants">
            <div
              v-for="u in booking.invited_users"
              :key="u.user_id"
              class="booking-detail__participant"
            >
              <n-tooltip
                v-if="!showEmails"
                trigger="hover"
                placement="top-start"
              >
                <template #trigger>
                  <span class="booking-detail__participant-name">{{ u.full_name }}</span>
                </template>
                {{ u.email }}
              </n-tooltip>
              <template v-else>
                <span class="booking-detail__participant-name">{{ u.full_name }}</span>
                <a
                  class="booking-detail__participant-email"
                  :href="`mailto:${u.email}`"
                >{{ u.email }}</a>
              </template>
            </div>
            <n-button
              size="tiny"
              quaternary
              class="booking-detail__toggle-emails"
              @click="showEmails = !showEmails"
            >
              {{ showEmails ? t('meetings.detail.hideEmails') : t('meetings.detail.showEmails') }}
            </n-button>
          </div>
        </div>
      </div>
    </template>
    <template #footer>
      <n-space justify="end">
        <n-button @click="visible = false">
          {{ t('common.close') }}
        </n-button>
        <n-button
          v-if="canEdit"
          type="error"
          @click="$emit('confirm-delete')"
        >
          {{ t('common.delete') }}
        </n-button>
        <n-button
          v-if="canEdit"
          type="primary"
          @click="$emit('edit')"
        >
          {{ t('common.edit') }}
        </n-button>
      </n-space>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NModal, NSpace, NTag, NIcon, NTooltip, NButton } from 'naive-ui'
import { VideocamOutline, LocationOutline } from '@vicons/ionicons5'
import type { BookingOut } from '../../api/meetings'

const props = defineProps<{
  show: boolean
  booking: BookingOut | null
  canEdit: boolean
}>()

const emit = defineEmits<{
  'update:show': [value: boolean]
  edit: []
  'confirm-delete': []
}>()

const { t, locale } = useI18n()

const showEmails = ref(false)

const visible = computed({
  get: () => props.show,
  set: (v) => emit('update:show', v),
})

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString(
    locale.value === 'ru' ? 'ru-RU' : 'en-GB',
    { hour: '2-digit', minute: '2-digit' },
  )
}
</script>

<style scoped>
.booking-detail {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.booking-detail__row {
  display: flex;
  gap: 12px;
  font-size: 14px;
}
.booking-detail__label {
  font-weight: 600;
  color: var(--color-text-muted);
  min-width: 110px;
  flex-shrink: 0;
}
.booking-detail__count {
  color: var(--color-text-muted);
  font-weight: 400;
  margin-left: 2px;
}
.booking-detail__rooms {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.booking-detail__participants {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.booking-detail__participant {
  display: flex;
  flex-direction: column;
  line-height: 1.35;
}
.booking-detail__participant-name {
  cursor: default;
}
.booking-detail__participant-email {
  font-size: 12px;
  color: var(--color-text-muted);
  text-decoration: none;
}
.booking-detail__participant-email:hover {
  text-decoration: underline;
}
.booking-detail__toggle-emails {
  align-self: flex-start;
  margin-top: 4px;
}
</style>
