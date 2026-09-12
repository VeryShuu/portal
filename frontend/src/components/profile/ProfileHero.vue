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
        <button
          v-if="user.avatar_url"
          type="button"
          class="profile-avatar-btn"
          :aria-label="t('users.profile.viewAvatar')"
          @click="openLightbox"
        >
          <UserAvatar
            :user="user"
            :size="96"
            :show-working-ring="true"
            class="profile-avatar"
          />
        </button>
        <UserAvatar
          v-else
          :user="user"
          :size="96"
          :show-working-ring="true"
          class="profile-avatar"
        />

        <div
          v-if="canManageAvatar"
          class="avatar-controls"
        >
          <n-upload
            accept="image/jpeg,image/png,image/webp"
            :show-file-list="false"
            :custom-request="handleAvatarUpload"
          >
            <button
              type="button"
              class="avatar-btn"
              :aria-label="t('users.profile.changeAvatar')"
            >
              <n-icon size="15">
                <CameraOutline />
              </n-icon>
            </button>
          </n-upload>
          <button
            v-if="user.avatar_url"
            type="button"
            class="avatar-btn"
            :aria-label="t('users.profile.avatarAdjust.title')"
            @click="adjustOpen = true"
          >
            <n-icon size="15">
              <CropOutline />
            </n-icon>
          </button>
          <n-popconfirm
            v-if="user.avatar_url"
            @positive-click="handleAvatarDelete"
          >
            <template #trigger>
              <button
                type="button"
                class="avatar-btn avatar-btn--danger"
                :aria-label="t('users.profile.deleteAvatar')"
              >
                <n-icon size="15">
                  <TrashOutline />
                </n-icon>
              </button>
            </template>
            {{ t('users.profile.deleteAvatarConfirm') }}
          </n-popconfirm>
        </div>
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
            v-if="user.current_status && user.current_status !== 'working'"
            class="profile-badge"
            :class="`profile-badge--${user.current_status}`"
          >
            <span class="profile-badge__dot" />
            {{ t(`users.presence.${user.current_status}`) }}
            <template v-if="user.current_status_until">
              · {{ t('users.presence.until', { date: untilLabel }) }}
            </template>
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

    <AvatarAdjustModal
      v-model:show="adjustOpen"
      :avatar-url="user.avatar_url"
      :focal-x="user.avatar_focal_x"
      :focal-y="user.avatar_focal_y"
      :focal-zoom="user.avatar_focal_zoom"
      :is-own="isOwn"
      :user-id="user.id"
      @saved="onFocalSaved"
    />

    <LightboxBase
      v-model="lightboxIdx"
      :total="1"
      :aria-label="t('users.profile.viewAvatar')"
      @wheel="lb.onLightboxWheel"
    >
      <img
        :src="user.avatar_url ?? undefined"
        :style="lb.imgStyle.value"
        class="profile-avatar-lightbox__img"
        alt=""
      >
      <template #toolbar>
        <div class="profile-avatar-lightbox__toolbar">
          <button
            :title="t('photos.lightbox.zoomOut')"
            @click="lb.zoomOut"
          >
            −
          </button>
          <span>{{ Math.round(lb.zoom.value * 100) }}%</span>
          <button
            :title="t('photos.lightbox.zoomIn')"
            @click="lb.zoomIn"
          >
            +
          </button>
          <button
            :title="t('photos.lightbox.rotate')"
            @click="lb.rotateLeft"
          >
            ⟲
          </button>
          <button
            :title="t('photos.lightbox.rotateRight')"
            @click="lb.rotateRight"
          >
            ⟳
          </button>
          <button
            :title="t('photos.lightbox.reset')"
            @click="lb.resetView"
          >
            ⤾
          </button>
        </div>
      </template>
    </LightboxBase>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQueryClient } from '@tanstack/vue-query'
import {
  NIcon,
  NPopconfirm,
  NUpload,
  useMessage,
  type UploadCustomRequestOptions,
} from 'naive-ui'
import {
  CameraOutline,
  CropOutline,
  KeyOutline,
  ShieldOutline,
  TrashOutline,
} from '@vicons/ionicons5'
import { useAuthStore } from '../../stores/auth'
import {
  adminDeleteUserAvatar,
  adminUploadUserAvatar,
  deleteAvatar,
  uploadAvatar,
  type UserPublic,
} from '../../api/users'
import type { UserMe } from '../../api/auth'
import { queryKeys } from '../../queries/keys'
import { parseApiError } from '../../utils/parseApiError'
import { formatDateShort } from '../../utils/formatDate'
import { useLightboxView } from '../../composables/useLightboxView'
import UserAvatar from '../UserAvatar.vue'
import AvatarAdjustModal from './AvatarAdjustModal.vue'
import LightboxBase from '../photos/LightboxBase.vue'

type DisplayUser = UserMe | UserPublic

const props = defineProps<{
  user: DisplayUser
  isOwn: boolean
}>()

const { t, locale } = useI18n()
const auth = useAuthStore()
const message = useMessage()
const queryClient = useQueryClient()

const adjustOpen = ref(false)
const lightboxIdx = ref<number | null>(null)
const lb = useLightboxView()

/** Менять аватар может владелец профиля и admin (управление прямо в профиле). */
const canManageAvatar = computed(() => props.isOwn || auth.isAdmin)

const untilLabel = computed(() =>
  props.user.current_status_until
    ? formatDateShort(props.user.current_status_until, locale.value)
    : '',
)

const roleLabel = computed(() => {
  if (!auth.user) return ''
  if (auth.user.role === 'admin') return t('admin.users.role.admin')
  if (auth.user.role === 'editor') return t('admin.users.role.editor')
  return t('admin.users.role.reader')
})

const authSourceLabel = computed(() =>
  auth.isLocalUser ? t('users.profile.authSource.local') : t('users.profile.authSource.keycloak'),
)

function openLightbox() {
  lb.resetView()
  lightboxIdx.value = 0
}

/** Обновить user-данные: свой профиль — auth-store, чужой — query-кэш. */
function applyUpdatedUser(updated: DisplayUser) {
  if (props.isOwn) {
    auth.setUser(updated as UserMe)
  } else {
    queryClient.setQueryData(queryKeys.users.detail(props.user.id), updated as UserPublic)
  }
}

async function handleAvatarUpload({ file, onFinish, onError }: UploadCustomRequestOptions) {
  try {
    if (props.isOwn) {
      applyUpdatedUser(await uploadAvatar(file.file as File))
    } else {
      applyUpdatedUser(await adminUploadUserAvatar(props.user.id, file.file as File))
    }
    message.success(t('users.profile.avatarUploaded'))
    adjustOpen.value = true
    onFinish()
  } catch (e) {
    message.error(parseApiError(e, t))
    onError()
  }
}

async function handleAvatarDelete() {
  try {
    if (props.isOwn) {
      applyUpdatedUser(await deleteAvatar())
    } else {
      applyUpdatedUser(await adminDeleteUserAvatar(props.user.id))
    }
    message.success(t('users.profile.avatarDeleted'))
  } catch (e) {
    message.error(parseApiError(e, t))
  }
}

function onFocalSaved(focal: { x: number | null; y: number | null; zoom: number | null }) {
  if (props.isOwn && auth.user) {
    auth.setUser({
      ...auth.user,
      avatar_focal_x: focal.x,
      avatar_focal_y: focal.y,
      avatar_focal_zoom: focal.zoom,
    })
  } else {
    queryClient.setQueryData<UserPublic | undefined>(
      queryKeys.users.detail(props.user.id),
      (old) =>
        old
          ? {
              ...old,
              avatar_focal_x: focal.x,
              avatar_focal_y: focal.y,
              avatar_focal_zoom: focal.zoom,
            }
          : old,
    )
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
.profile-avatar-btn {
  padding: 0;
  border: 0;
  background: none;
  cursor: zoom-in;
  line-height: 0;
  border-radius: 50%;
}
.profile-avatar {
  border: 3px solid rgba(255, 255, 255, 0.85);
  box-shadow: var(--shadow-md);
}

/* Контролы аватара: загрузить / подогнать / удалить. */
.avatar-controls {
  position: absolute;
  right: -4px;
  bottom: -4px;
  display: flex;
  gap: 4px;
}
.avatar-btn {
  width: 28px;
  height: 28px;
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
.avatar-btn:hover {
  background: var(--color-brand-red-hover);
  transform: scale(1.05);
}
.avatar-btn--danger:hover {
  background: var(--color-error, #d03050);
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
.profile-badge--vacation { color: var(--presence-ring-vacation); }
.profile-badge--sick { color: var(--presence-ring-sick); }
.profile-badge--business_trip { color: var(--presence-ring-business_trip); }

/* Лайтбокс аватара (просмотр с зумом). */
.profile-avatar-lightbox__img {
  max-width: 92vw;
  max-height: 88vh;
  object-fit: contain;
  user-select: none;
  -webkit-user-drag: none;
}
.profile-avatar-lightbox__toolbar {
  position: absolute;
  top: 16px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 6px;
  background: rgba(0, 0, 0, 0.55);
  padding: 6px 10px;
  border-radius: 999px;
  z-index: 3;
}
.profile-avatar-lightbox__toolbar button {
  background: rgba(255, 255, 255, 0.12);
  color: #fff;
  border: 0;
  cursor: pointer;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  font-size: 16px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.profile-avatar-lightbox__toolbar button:hover {
  background: rgba(255, 255, 255, 0.22);
}
.profile-avatar-lightbox__toolbar span {
  color: #fff;
  font-size: 12px;
  min-width: 44px;
  text-align: center;
}

@media (max-width: 640px) {
  .profile-hero__inner { flex-direction: column; align-items: flex-start; padding: 22px; }
  .profile-hero__name { font-size: 22px; }
}
</style>
