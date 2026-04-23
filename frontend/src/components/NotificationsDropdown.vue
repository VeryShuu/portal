<template>
  <n-popover
    trigger="click"
    placement="bottom-end"
    :width="360"
    :show="store.dropdownOpen"
    @update:show="store.dropdownOpen = $event"
    @show="onOpen"
  >
    <template #trigger>
      <n-tooltip placement="bottom">
        <template #trigger>
          <n-button
            quaternary
            circle
            class="header-icon-btn"
            :aria-label="t('nav.notifications')"
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
    </template>

    <div class="notif-panel">
      <div class="notif-panel__head">
        <span class="notif-panel__title">{{ t('notifications.title') }}</span>
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

      <div v-if="store.loading" class="notif-panel__spinner">
        <n-spin size="small" />
      </div>

      <div v-else-if="store.items.length === 0" class="notif-panel__empty">
        <n-icon size="32" class="notif-panel__empty-icon"><NotificationsOffOutline /></n-icon>
        <p>{{ t('notifications.empty') }}</p>
      </div>

      <n-scrollbar v-else style="max-height: 420px">
        <div class="notif-list">
          <div
            v-for="n in store.items"
            :key="n.id"
            class="notif-item"
            :class="{ 'notif-item--unread': !n.is_read }"
            @click="handleItemClick(n)"
          >
            <div class="notif-item__dot" v-if="!n.is_read" />
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
      </n-scrollbar>
    </div>
  </n-popover>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { NPopover, NButton, NIcon, NBadge, NTooltip, NScrollbar, NSpin } from 'naive-ui'
import { NotificationsOutline, NotificationsOffOutline, CloseOutline } from '@vicons/ionicons5'
import { useNotificationsStore } from '../stores/notifications'
import type { NotificationItem } from '../api/notifications'

const store = useNotificationsStore()
const router = useRouter()
const { t } = useI18n()
const markingAll = ref(false)

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

async function onOpen() {
  await store.loadNotifications()
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
  store.dropdownOpen = false
  if (n.link) router.push(n.link)
}
</script>

<style scoped>
.notif-panel {
  padding: 0;
}

.notif-panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px 8px;
  border-bottom: 1px solid var(--color-border, #e8e8e8);
}

.notif-panel__title {
  font-weight: 600;
  font-size: 14px;
}

.notif-panel__spinner,
.notif-panel__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 32px 16px;
  gap: 8px;
  color: var(--n-text-color-disabled, #bbb);
}

.notif-panel__empty-icon {
  opacity: 0.4;
}

.notif-panel__empty p {
  margin: 0;
  font-size: 13px;
}

.notif-list {
  padding: 4px 0;
}

.notif-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 16px;
  cursor: pointer;
  transition: background 0.15s;
  position: relative;
}

.notif-item:hover {
  background: var(--n-color-hover, rgba(0,0,0,0.04));
}

.notif-item--unread {
  background: var(--n-color-hover, rgba(20,58,102,0.05));
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
  color: var(--n-text-color-3, #888);
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.notif-item__time {
  font-size: 11px;
  color: var(--n-text-color-disabled, #aaa);
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
