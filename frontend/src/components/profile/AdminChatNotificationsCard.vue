<template>
  <section class="profile-card">
    <header class="profile-card__head">
      <h2 class="profile-card__title">
        {{ t('users.profile.sections.notificationsAdmin') }}
      </h2>
    </header>

    <n-spin :show="loading">
      <div class="pref-row">
        <div class="pref-row__text">
          <div class="pref-row__label">
            {{ t('users.notifications.chat') }}
          </div>
          <div class="pref-row__hint">
            {{ t('users.notifications.chatAdminHint') }}
          </div>
        </div>
        <n-switch
          :value="enabled"
          :loading="saving"
          :disabled="loading"
          @update:value="onToggle"
        />
      </div>
    </n-spin>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { NSpin, NSwitch, useMessage } from 'naive-ui'
import {
  fetchAdminNotificationPreferences,
  patchAdminNotificationPreferences,
} from '../../api/users'
import { parseApiError } from '../../utils/parseApiError'

const props = defineProps<{ userId: string }>()

const { t } = useI18n()
const message = useMessage()

const loading = ref(true)
const saving = ref(false)
const enabled = ref(false)

;(async () => {
  try {
    const prefs = await fetchAdminNotificationPreferences(props.userId)
    enabled.value = prefs.chat_notifications_enabled
  } catch (e) {
    message.error(parseApiError(e, t))
  } finally {
    loading.value = false
  }
})()

async function onToggle(value: boolean) {
  saving.value = true
  try {
    const prefs = await patchAdminNotificationPreferences(props.userId, {
      chat_notifications_enabled: value,
    })
    enabled.value = prefs.chat_notifications_enabled
    message.success(t('common.save'))
  } catch (e) {
    message.error(parseApiError(e, t))
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.profile-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 22px 24px;
  box-shadow: var(--shadow-sm);
}
.profile-card__head {
  margin-bottom: 16px;
}
.profile-card__title {
  margin: 0;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--color-text-muted);
}
.pref-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 0;
  border-top: 1px solid var(--color-border);
}
.pref-row__label {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text);
}
.pref-row__hint {
  font-size: 12px;
  color: var(--color-text-muted);
  margin-top: 4px;
}
</style>
