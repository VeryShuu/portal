<template>
  <section
    v-if="show"
    class="widget"
  >
    <div class="widget__header">
      <h3 class="widget__title">
        {{ t('meetings.widget.title') }}
      </h3>
      <router-link
        class="widget__link"
        to="/meetings"
      >
        {{ t('meetings.widget.viewAll') }}
      </router-link>
    </div>

    <div
      v-if="isLoading"
      class="meetings-widget__skeleton"
    >
      <div
        v-for="i in 3"
        :key="`msk-${i}`"
        class="meetings-widget__skeleton-row"
      />
    </div>

    <ul
      v-else-if="bookings.length"
      class="meetings-widget__list"
    >
      <li
        v-for="b in bookings"
        :key="b.id"
        class="meetings-widget__item"
      >
        <div class="meetings-widget__time">
          {{ formatTime(b.start_time) }}–{{ formatTime(b.end_time) }}
        </div>
        <div class="meetings-widget__info">
          <div class="meetings-widget__item-title">
            {{ b.title }}
          </div>
          <div class="meetings-widget__rooms">
            {{ b.rooms.map(r => r.name).join(', ') }}
          </div>
        </div>
      </li>
    </ul>

    <div
      v-else
      class="meetings-widget__empty"
    >
      <p class="meetings-widget__empty-title">
        {{ t('meetings.widget.noMeetings') }}
      </p>
      <p class="meetings-widget__empty-hint">
        {{ t('home.meetings.noMeetingsHint') }}
      </p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import { useQueryClient } from '@tanstack/vue-query'
import { useModulesStore } from '@/stores/modules'
import { useMyMeetingBookingsQuery } from '@/queries/meetings'
import { queryKeys } from '@/queries/keys'

const { t, locale } = useI18n()
const modulesStore = useModulesStore()
const qc = useQueryClient()

const show = computed(() => modulesStore.isEnabled('meetings'))

const { data, isLoading } = useMyMeetingBookingsQuery({ limit: 5 }, { enabled: show })
const bookings = computed(() => data.value ?? [])

function loc(): string {
  return locale.value === 'ru' ? 'ru-RU' : 'en-GB'
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  const today = new Date()
  const sameDay =
    d.getFullYear() === today.getFullYear() &&
    d.getMonth() === today.getMonth() &&
    d.getDate() === today.getDate()
  const time = d.toLocaleTimeString(loc(), { hour: '2-digit', minute: '2-digit' })
  if (sameDay) return time
  const date = d.toLocaleDateString(loc(), { day: '2-digit', month: '2-digit' })
  return `${date} ${time}`
}

function handleMeetingsChanged() {
  qc.invalidateQueries({ queryKey: queryKeys.meetings.myBookings({}) })
}

onMounted(() => {
  modulesStore.load()
  window.addEventListener('meetings:changed', handleMeetingsChanged)
})

onBeforeUnmount(() => {
  window.removeEventListener('meetings:changed', handleMeetingsChanged)
})
</script>

<style scoped>
.widget {
  background: var(--color-mage-card, var(--color-surface));
  border: 1px solid var(--color-mage-border, var(--color-border));
  border-radius: var(--radius-card, var(--radius-lg));
  padding: var(--space-card-inner, 16px) var(--space-card-inner, 18px) calc(var(--space-card-inner, 16px) - 4px);
  box-shadow: var(--shadow-soft, var(--shadow-sm));
}
.widget__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.widget__title {
  margin: 0;
  font-size: 13px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--color-text-muted);
}
.widget__link {
  font-size: 12px;
  color: var(--color-brand-red);
  text-decoration: none;
}
.widget__link:hover { text-decoration: underline; }

.meetings-widget__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.meetings-widget__item {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}
.meetings-widget__time {
  font-size: 12px;
  color: var(--color-text-muted);
  min-width: 80px;
  flex-shrink: 0;
  padding-top: 1px;
}
.meetings-widget__info {
  flex: 1;
  min-width: 0;
}
.meetings-widget__item-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.meetings-widget__rooms {
  font-size: 11px;
  color: var(--color-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.meetings-widget__empty {
  /* Компактный empty-state (ТЗ п.7): без большого пустого пространства */
  margin: 4px 0 0;
  text-align: center;
  padding: 4px 0;
}
.meetings-widget__empty-title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-mage-text, var(--color-text));
}
.meetings-widget__empty-hint {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--color-mage-text-secondary, var(--color-text-muted));
}
.meetings-widget__skeleton {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.meetings-widget__skeleton-row {
  height: 32px;
  border-radius: var(--radius-sm);
  background: linear-gradient(90deg, var(--color-bg-muted) 25%, var(--color-border) 50%, var(--color-bg-muted) 75%);
  background-size: 200% 100%;
  animation: skeleton-shimmer 1.4s infinite;
}
@keyframes skeleton-shimmer {
  0%   { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
</style>
