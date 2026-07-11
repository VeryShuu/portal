<template>
  <section class="profile-hero">
    <div
      class="profile-hero__bg"
      aria-hidden="true"
    >
      <svg
        viewBox="0 0 1200 300"
        preserveAspectRatio="xMidYMid slice"
      >
        <defs>
          <linearGradient
            id="profile-wave"
            x1="0"
            y1="0"
            x2="1"
            y2="1"
          >
            <stop
              offset="0%"
              stop-color="#4a90c4"
              stop-opacity="0.22"
            />
            <stop
              offset="100%"
              stop-color="#143a66"
              stop-opacity="0.05"
            />
          </linearGradient>
        </defs>
        <path
          fill="url(#profile-wave)"
          d="M0,200 C200,260 420,160 620,200 C820,240 1020,280 1200,220 L1200,300 L0,300 Z"
        />
        <path
          fill="rgba(255,255,255,0.06)"
          d="M0,240 C220,280 440,220 660,240 C880,260 1080,300 1200,260 L1200,300 L0,300 Z"
        />
      </svg>
    </div>

    <div class="profile-hero__inner">
      <div class="profile-avatar-wrap">
        <n-avatar
          round
          :size="96"
          :src="user.avatar_url ?? undefined"
          class="profile-avatar"
        >
          <template v-if="!user.avatar_url">
            {{ initials }}
          </template>
        </n-avatar>
        <n-upload
          v-if="isOwn"
          accept="image/jpeg,image/png,image/webp"
          :show-file-list="false"
          :custom-request="handleAvatarUpload"
          class="avatar-upload"
        >
          <button
            type="button"
            class="avatar-edit"
            :aria-label="t('users.profile.changeAvatar')"
          >
            <n-icon size="16">
              <CameraOutline />
            </n-icon>
          </button>
        </n-upload>
      </div>

      <div class="profile-hero__info">
        <h1 class="profile-hero__name">
          {{ user.full_name }}
        </h1>
        <div class="profile-hero__meta">
          <span v-if="user.position">{{ user.position }}</span>
          <span
            v-if="user.position && user.department"
            class="profile-hero__dot"
          >•</span>
          <span v-if="user.department">{{ user.department }}</span>
        </div>
        <div class="profile-hero__badges">
          <span
            class="profile-badge"
            :class="`profile-badge--${user.presence_status}`"
          >
            <span class="profile-badge__dot" />
            {{ t(`users.profile.status.${user.presence_status}`) }}
          </span>
          <template v-if="isOwn">
            <span class="profile-badge profile-badge--role">
              <n-icon size="12"><ShieldOutline /></n-icon>
              {{ roleLabel }}
            </span>
            <span class="profile-badge profile-badge--auth">
              <n-icon size="12"><KeyOutline /></n-icon>
              {{ authSourceLabel }}
            </span>
          </template>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NAvatar, NUpload, NIcon, useMessage, type UploadCustomRequestOptions } from 'naive-ui'
import { CameraOutline, ShieldOutline, KeyOutline } from '@vicons/ionicons5'
import { useAuthStore } from '../../stores/auth'
import { uploadAvatar, type UserPublic } from '../../api/users'
import type { UserMe } from '../../api/auth'
import { parseApiError } from '../../utils/parseApiError'

type DisplayUser = UserMe | UserPublic

const props = defineProps<{
  user: DisplayUser
  isOwn: boolean
}>()

const { t } = useI18n()
const auth = useAuthStore()
const message = useMessage()

const initials = computed(() => {
  const name = props.user.full_name ?? ''
  return name.split(' ').slice(0, 2).map((w: string) => w[0]).join('').toUpperCase()
})

const roleLabel = computed(() => {
  if (!auth.user) return ''
  if (auth.user.role === 'admin') return t('admin.users.role.admin')
  if (auth.user.role === 'editor') return t('admin.users.role.editor')
  return t('admin.users.role.reader')
})

const authSourceLabel = computed(() =>
  auth.isLocalUser ? t('users.profile.authSource.local') : t('users.profile.authSource.keycloak'),
)

async function handleAvatarUpload({ file, onFinish, onError }: UploadCustomRequestOptions) {
  try {
    const updated = await uploadAvatar(file.file as File)
    auth.setUser(updated)
    message.success(t('users.profile.changeAvatar'))
    onFinish()
  } catch (e) {
    message.error(parseApiError(e, t))
    onError()
  }
}
</script>

<style scoped>
.profile-hero {
  position: relative;
  border-radius: var(--radius-xl);
  overflow: hidden;
  background: var(--gradient-hero);
  color: #fff;
  box-shadow: var(--shadow-md);
  margin-bottom: 24px;
}
.profile-hero__bg {
  position: absolute;
  inset: 0;
  pointer-events: none;
}
.profile-hero__bg svg {
  width: 100%;
  height: 100%;
}
.profile-hero__inner {
  position: relative;
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 28px 32px;
}

.profile-avatar-wrap {
  position: relative;
  flex-shrink: 0;
}
.profile-avatar {
  border: 3px solid rgba(255, 255, 255, 0.85);
  box-shadow: var(--shadow-md);
}
.avatar-upload {
  position: absolute;
  right: -4px;
  bottom: -4px;
}
.avatar-edit {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--color-brand-red);
  color: #fff;
  border: 2px solid #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background var(--t-fast), transform var(--t-fast);
}
.avatar-edit:hover {
  background: var(--color-brand-red-hover);
  transform: scale(1.05);
}

.profile-hero__info {
  flex: 1;
  min-width: 0;
}
.profile-hero__name {
  margin: 0 0 6px;
  font-size: 26px;
  font-weight: 800;
  letter-spacing: -0.02em;
  color: #fff;
}
.profile-hero__meta {
  color: rgba(255, 255, 255, 0.82);
  font-size: 14px;
  margin-bottom: 14px;
}
.profile-hero__dot {
  margin: 0 6px;
  opacity: 0.6;
}
.profile-hero__badges {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.profile-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border-radius: var(--radius-pill);
  background: rgba(255, 255, 255, 0.14);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  backdrop-filter: blur(4px);
}
.profile-badge__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
}
.profile-badge--office { color: #86efac; }
.profile-badge--remote { color: #fcd34d; }
.profile-badge--vacation { color: #fca5a5; }

@media (max-width: 640px) {
  .profile-hero__inner { flex-direction: column; align-items: flex-start; padding: 22px; }
  .profile-hero__name { font-size: 22px; }
}
</style>
