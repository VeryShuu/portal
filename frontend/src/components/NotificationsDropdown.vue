<template>
  <n-tooltip placement="bottom">
    <template #trigger>
      <n-button
        quaternary
        circle
        class="header-icon-btn"
        :aria-label="t('nav.notifications')"
        @click="openDrawer"
      >
        <template #icon>
          <n-badge :value="store.unreadCount" :max="99" :show="store.hasUnread" dot>
            <n-icon><NotificationsOutline /></n-icon>
          </n-badge>
        </template>
      </n-button>
    </template>
    {{ t('nav.notifications') }}
  </n-tooltip>

  <n-drawer
    v-model:show="drawerVisible"
    placement="right"
    :width="360"
    :trap-focus="false"
  >
    <n-drawer-content closable>
      <template #header>
        <div class="notif-drawer-head">
          <span class="notif-drawer-title">{{ t('notifications.title') }}</span>
          <n-button
            v-if="store.hasUnread"
            text
            size="small"
            :loading="markingAll"
            @click="handleReadAll"
          >
            {{ t('notifications.markAllRead') }}
          </n-button>
        </div>
      </template>

      <div v-if="store.loading" class="notif-panel__spinner">
        <n-spin size="small" />
      </div>

      <div v-else-if="store.items.length === 0" class="notif-panel__empty">
        <n-icon size="32" class="notif-panel__empty-icon"><NotificationsOffOutline /></n-icon>
        <p>{{ t('notifications.empty') }}</p>
      </div>

      <template v-else>
        <div
          v-for="group in groupedNotifications"
          :key="group.label"
          class="notif-group"
        >
          <div class="notif-group__label">{{ group.label }}</div>
          <div
            v-for="n in group.items"
            :key="n.id"
            class="notif-item"
            :class="{ 'notif-item--unread': !n.is_read }"
            @click="handleItemClick(n)"
          >
            <div v-if="!n.is_read" class="notif-item__dot" />
            <div class="notif-item__body">
              <div class="notif-item__title">{{ n.title }}</div>
              <div v-if="n.body" class="notif-item__sub">{{ n.body }}</div>
              <div class="notif-item__time">{{ formatTime(n.created_at) }}</div>
            </div>
            <n-button
              text
              size="tiny"
              class="notif-item__del"
              :aria-label="t('notifications.delete')"
              @click.stop="store.remove(n.id)"
            >
              <template #icon><n-icon><CloseOutline /></n-icon></template>
            </n-button>
          </div>
        </div>
      </template>
    </n-drawer-content>
  </n-drawer>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { NDrawer, NDrawerContent, NButton, NIcon, NBadge, NTooltip, NSpin } from 'naive-ui'
import { NotificationsOutline, NotificationsOffOutline, CloseOutline } from '@vicons/ionicons5'
import { useNotificationsStore } from '../stores/notifications'
import type { NotificationItem } from '../api/notifications'

const store = useNotificationsStore()
const router = useRouter()
const { t } = useI18n()
const markingAll = ref(false)
const drawerVisible = ref(false)

function openDrawer() {
  drawerVisible.value = true
  store.loadNotifications()
}

function isSameDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
}

interface NotifGroup {
  label: string
  items: NotificationItem[]
}

const groupedNotifications = computed<NotifGroup[]>(() => {
  const today = new Date()
  const yesterday = new Date(today)
  yesterday.setDate(today.getDate() - 1)

  const groups: NotifGroup[] = [
    { label: t('notifications.today'), items: [] },
    { label: t('notifications.yesterday'), items: [] },
    { label: t('notifications.earlier'), items: [] },
  ]

  for (const n of store.items) {
    const d = new Date(n.created_at)
    if (isSameDay(d, today)) {
      groups[0].items.push(n)
    } else if (isSameDay(d, yesterday)) {
      groups[1].items.push(n)
    } else {
      groups[2].items.push(n)
    }
  }

  return groups.filter(g => g.items.length > 0)
})

function formatTime(iso: string): string {
  const d = new Date(iso)
  const now = new Date()
  const diffMs = now.getTime() - d.getTime()
  const diffMin = Math.floor(diffMs / 60000)
  if (diffMin < 1) return t('notifications.justNow')
  if (diffMin < 60) return t('notifications.minutesAgo', { n: diffMin })
  const diffH = Math.floor(diffMin / 60)
  if (diffH < 24) return t('notifications.hoursAgo', { n: diffH })
  return d.toLocaleDateString()
}

async function handleReadAll() {
  markingAll.value = true
  try {
    await store.readAll()
  } finally {
    markingAll.value = false
  }
}

async function handleItemClick(n: NotificationItem) {
  if (!n.is_read) await store.read(n.id)
  drawerVisible.value = false
  if (n.link) router.push(n.link)
}
</script>

<style scoped>
.notif-drawer-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  gap: 12px;
}

.notif-drawer-title {
  font-weight: 600;
  font-size: 15px;
}

.notif-group__label {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--color-text-subtle);
  padding: 10px 4px 4px;
}

.notif-group + .notif-group {
  margin-top: 4px;
}

.notif-panel__spinner,
.notif-panel__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 16px;
  gap: 8px;
  color: var(--color-text-subtle);
}

.notif-panel__empty-icon {
  opacity: 0.4;
}

.notif-panel__empty p {
  margin: 0;
  font-size: 13px;
}

.notif-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 4px;
  cursor: pointer;
  border-radius: var(--radius-md);
  transition: background 0.15s;
  position: relative;
}

.notif-item:hover {
  background: var(--color-bg-muted);
}

.notif-item--unread {
  background: rgba(20, 58, 102, 0.05);
}

[data-theme='dark'] .notif-item--unread {
  background: rgba(255, 255, 255, 0.05);
}

.notif-item__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-brand-red, #d8262c);
  flex-shrink: 0;
  margin-top: 5px;
}

.notif-item__body {
  flex: 1;
  min-width: 0;
}

.notif-item__title {
  font-size: 13px;
  font-weight: 500;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.notif-item__sub {
  font-size: 12px;
  color: var(--color-text-muted);
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.notif-item__time {
  font-size: 11px;
  color: var(--color-text-subtle);
  margin-top: 4px;
}

.notif-item__del {
  opacity: 0;
  flex-shrink: 0;
}

.notif-item:hover .notif-item__del {
  opacity: 1;
}
</style>
