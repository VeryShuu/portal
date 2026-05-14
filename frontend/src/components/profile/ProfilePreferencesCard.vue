<template>
  <section class="profile-card">
    <header class="profile-card__head">
      <h2 class="profile-card__title">{{ t('users.profile.sections.preferences') }}</h2>
    </header>
    <n-form :model="form" label-placement="top">
      <n-form-item :label="t('users.profile.status.label')">
        <n-select v-model:value="form.presence_status" :options="statusOptions" />
      </n-form-item>
      <div class="pref-row">
        <div class="pref-row__text">
          <div class="pref-row__label">{{ t('users.notifications.email') }}</div>
        </div>
        <n-switch v-model:value="form.notify_email" />
      </div>
      <div class="pref-row">
        <div class="pref-row__text">
          <div class="pref-row__label">{{ t('users.notifications.inapp') }}</div>
        </div>
        <n-switch v-model:value="form.notify_inapp" />
      </div>
    </n-form>
    <div class="card-actions">
      <n-button type="primary" :loading="saving" @click="save">
        {{ t('users.profile.save') }}
      </n-button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NForm, NFormItem, NSelect, NSwitch, NButton, useMessage,
} from 'naive-ui'
import { useAuthStore } from '../../stores/auth'
import { patchMyProfile } from '../../api/users'

const { t } = useI18n()
const auth = useAuthStore()
const message = useMessage()

const form = ref({
  presence_status: (auth.user?.presence_status ?? 'office') as 'office' | 'remote' | 'vacation',
  notify_email: auth.user?.notify_email ?? true,
  notify_inapp: auth.user?.notify_inapp ?? true,
})

const saving = ref(false)

const statusOptions = computed(() => [
  { label: t('users.profile.status.office'), value: 'office' },
  { label: t('users.profile.status.remote'), value: 'remote' },
  { label: t('users.profile.status.vacation'), value: 'vacation' },
])

watch(() => auth.user, (u) => {
  if (u) {
    form.value.presence_status = u.presence_status
    form.value.notify_email = u.notify_email
    form.value.notify_inapp = u.notify_inapp
  }
})

async function save() {
  saving.value = true
  try {
    const updated = await patchMyProfile(form.value)
    auth.setUser(updated)
    message.success(t('common.save'))
  } catch {
    message.error(t('errors.generic'))
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
.card-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
