<template>
  <section class="profile-card">
    <header class="profile-card__head">
      <h2 class="profile-card__title">
        {{ t('users.profile.sections.preferences') }}
      </h2>
    </header>
    <n-form
      :model="form"
      label-placement="top"
    >
      <div class="pref-row">
        <div class="pref-row__text">
          <div class="pref-row__label">
            {{ t('users.notifications.email') }}
          </div>
        </div>
        <n-switch v-model:value="form.notify_email" />
      </div>
      <div class="pref-row">
        <div class="pref-row__text">
          <div class="pref-row__label">
            {{ t('users.notifications.inapp') }}
          </div>
        </div>
        <n-switch v-model:value="form.notify_inapp" />
      </div>
      <div class="pref-row">
        <div class="pref-row__text">
          <div class="pref-row__label">
            {{ t('users.notifications.chat') }}
          </div>
          <div class="pref-row__hint">
            {{ t('users.notifications.chatHint') }}
          </div>
        </div>
        <n-switch v-model:value="form.chat_notifications_enabled" />
      </div>
    </n-form>
    <div class="card-actions">
      <n-button
        type="primary"
        :loading="saving"
        @click="save"
      >
        {{ t('users.profile.save') }}
      </n-button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NForm, NSwitch, NButton, useMessage } from 'naive-ui'
import { useAuthStore } from '../../stores/auth'
import { patchMyPreferences, patchMyProfile } from '../../api/users'
import { parseApiError } from '../../utils/parseApiError'

const { t } = useI18n()
const auth = useAuthStore()
const message = useMessage()

// chat-флаг живёт в preferences JSONB (сохраняется через /me/preferences),
// email/inapp — отдельные колонки (через /me/profile): две точки записи,
// одна кнопка Save.
const form = ref({
  notify_email: auth.user?.notify_email ?? true,
  notify_inapp: auth.user?.notify_inapp ?? true,
  chat_notifications_enabled:
    auth.user?.preferences?.chat_notifications_enabled === true,
})

const saving = ref(false)

watch(() => auth.user, (u) => {
  if (u) {
    form.value.notify_email = u.notify_email
    form.value.notify_inapp = u.notify_inapp
    form.value.chat_notifications_enabled =
      u.preferences?.chat_notifications_enabled === true
  }
})

async function save() {
  saving.value = true
  try {
    const [updated] = await Promise.all([
      patchMyProfile({
        notify_email: form.value.notify_email,
        notify_inapp: form.value.notify_inapp,
      }),
      patchMyPreferences({
        chat_notifications_enabled: form.value.chat_notifications_enabled,
      }),
    ])
    auth.setUser(updated)
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
.card-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
