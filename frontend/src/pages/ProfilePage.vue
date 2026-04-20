<template>
  <AppLayout>
    <template #header-title>
      <span>{{ t('users.profile.title') }}</span>
    </template>

    <div class="profile-wrap">
      <n-card style="max-width:600px;margin:0 auto">
        <div class="avatar-row">
          <n-avatar
            round
            :size="80"
            :src="auth.user?.avatar_url ?? undefined"
          >
            <template v-if="!auth.user?.avatar_url">{{ initials }}</template>
          </n-avatar>
          <n-upload
            accept="image/jpeg,image/png,image/webp"
            :show-file-list="false"
            :custom-request="handleAvatarUpload"
          >
            <n-button size="small">{{ t('users.profile.changeAvatar') }}</n-button>
          </n-upload>
        </div>

        <n-descriptions bordered :column="1" style="margin-top:16px">
          <n-descriptions-item :label="t('users.fields.fullName')">{{ auth.user?.full_name }}</n-descriptions-item>
          <n-descriptions-item :label="t('users.fields.email')">{{ auth.user?.email }}</n-descriptions-item>
          <n-descriptions-item :label="t('users.fields.department')">{{ auth.user?.department ?? '—' }}</n-descriptions-item>
          <n-descriptions-item :label="t('users.fields.position')">{{ auth.user?.position ?? '—' }}</n-descriptions-item>
          <n-descriptions-item :label="t('users.fields.phone')">{{ auth.user?.phone ?? '—' }}</n-descriptions-item>
        </n-descriptions>

        <n-divider />

        <n-form :model="form" label-placement="top">
          <n-form-item :label="t('users.profile.status.label')">
            <n-select v-model:value="form.presence_status" :options="statusOptions" />
          </n-form-item>

          <n-form-item :label="t('users.notifications.email')">
            <n-switch v-model:value="form.notify_email" />
          </n-form-item>

          <n-form-item :label="t('users.notifications.inapp')">
            <n-switch v-model:value="form.notify_inapp" />
          </n-form-item>
        </n-form>

        <div class="actions">
          <n-button type="primary" :loading="saving" @click="save">{{ t('users.profile.save') }}</n-button>
        </div>
      </n-card>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NCard, NAvatar, NUpload, NButton, NDescriptions, NDescriptionsItem,
  NDivider, NForm, NFormItem, NSelect, NSwitch,
  useMessage, type UploadCustomRequestOptions,
} from 'naive-ui'
import AppLayout from '../components/AppLayout.vue'
import { useAuthStore } from '../stores/auth'
import { patchMyProfile, uploadAvatar } from '../api/users'

const auth = useAuthStore()
const { t } = useI18n()
const message = useMessage()
const saving = ref(false)

const initials = computed(() => {
  const name = auth.user?.full_name ?? ''
  return name.split(' ').slice(0, 2).map((w: string) => w[0]).join('').toUpperCase()
})

const form = ref({
  presence_status: auth.user?.presence_status ?? 'office' as 'office' | 'remote' | 'vacation',
  notify_email: auth.user?.notify_email ?? true,
  notify_inapp: auth.user?.notify_inapp ?? true,
})

onMounted(() => {
  form.value.presence_status = auth.user?.presence_status ?? 'office'
  form.value.notify_email = auth.user?.notify_email ?? true
  form.value.notify_inapp = auth.user?.notify_inapp ?? true
})

const statusOptions = [
  { label: t('users.profile.status.office'), value: 'office' },
  { label: t('users.profile.status.remote'), value: 'remote' },
  { label: t('users.profile.status.vacation'), value: 'vacation' },
]

async function save() {
  saving.value = true
  try {
    const updated = await patchMyProfile(form.value)
    auth.user = updated
    message.success(t('common.save'))
  } catch {
    message.error(t('errors.generic'))
  } finally {
    saving.value = false
  }
}

async function handleAvatarUpload({ file, onFinish, onError }: UploadCustomRequestOptions) {
  try {
    const updated = await uploadAvatar(file.file as File)
    auth.user = updated
    message.success(t('users.profile.changeAvatar'))
    onFinish()
  } catch {
    message.error(t('errors.generic'))
    onError()
  }
}
</script>

<style scoped>
.profile-wrap { max-width: 700px; margin: 0 auto; }
.avatar-row { display: flex; align-items: center; gap: 16px; }
.actions { display: flex; justify-content: flex-end; margin-top: 16px; }
</style>
