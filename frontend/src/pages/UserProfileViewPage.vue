<template>
  <div class="upv-wrap">
    <n-spin v-if="loading" style="margin:60px auto;display:block" />

    <template v-else-if="user">
      <section class="profile-hero">
        <div class="profile-hero__bg" aria-hidden="true">
          <svg viewBox="0 0 1200 300" preserveAspectRatio="xMidYMid slice">
            <defs>
              <linearGradient id="upv-wave" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stop-color="#4a90c4" stop-opacity="0.22"/>
                <stop offset="100%" stop-color="#143a66" stop-opacity="0.05"/>
              </linearGradient>
            </defs>
            <path fill="url(#upv-wave)" d="M0,200 C200,260 420,160 620,200 C820,240 1020,280 1200,220 L1200,300 L0,300 Z"/>
            <path fill="rgba(255,255,255,0.06)" d="M0,240 C220,280 440,220 660,240 C880,260 1080,300 1200,260 L1200,300 L0,300 Z"/>
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
              <template v-if="!user.avatar_url">{{ initials }}</template>
            </n-avatar>
          </div>

          <div class="profile-hero__info">
            <h1 class="profile-hero__name">{{ user.full_name }}</h1>
            <div class="profile-hero__meta">
              <span v-if="user.position">{{ user.position }}</span>
              <span v-if="user.position && user.department" class="profile-hero__dot">•</span>
              <span v-if="user.department">{{ user.department }}</span>
            </div>
            <div class="profile-hero__badges">
              <span class="profile-badge" :class="`profile-badge--${user.presence_status}`">
                <span class="profile-badge__dot" />
                {{ t(`users.profile.status.${user.presence_status}`) }}
              </span>
            </div>
          </div>
        </div>
      </section>

      <div class="upv-grid">
        <section class="profile-card">
          <header class="profile-card__head">
            <h2 class="profile-card__title">{{ t('users.profile.sections.info') }}</h2>
          </header>
          <dl class="info-list">
            <div class="info-row">
              <dt>{{ t('users.fields.email') }}</dt>
              <dd>{{ user.email }}</dd>
            </div>
            <div class="info-row">
              <dt>{{ t('users.fields.phone') }}</dt>
              <dd>{{ user.phone ?? '—' }}</dd>
            </div>
            <div class="info-row">
              <dt>{{ t('users.fields.department') }}</dt>
              <dd>{{ user.department ?? '—' }}</dd>
            </div>
            <div class="info-row">
              <dt>{{ t('users.fields.position') }}</dt>
              <dd>{{ user.position ?? '—' }}</dd>
            </div>
          </dl>
        </section>

        <section v-if="auth.isAdmin" class="profile-card">
          <header class="profile-card__head">
            <h2 class="profile-card__title">{{ t('users.profile.sections.groups') }}</h2>
          </header>
          <div v-if="groupsLoading" class="upv-groups-loading">
            <n-spin size="small" />
          </div>
          <div v-else-if="groups.length" class="upv-groups">
            <n-tag
              v-for="g in groups"
              :key="g"
              size="medium"
              :bordered="false"
              class="upv-group-tag"
            >
              {{ g }}
            </n-tag>
          </div>
          <div v-else class="upv-groups-empty">
            {{ t('users.profile.noGroups') }}
          </div>
        </section>
      </div>
    </template>

    <div v-else class="upv-notfound">
      <n-result status="404" :title="t('users.notFound')" :description="t('errors.notFound.description')">
        <template #footer>
          <n-button @click="router.back()">{{ t('common.back') }}</n-button>
        </template>
      </n-result>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { NAvatar, NSpin, NResult, NButton, NTag } from 'naive-ui'
import { fetchUserById, adminFetchUserKeycloakGroups, type UserPublic } from '../api/users'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const auth = useAuthStore()

const user = ref<UserPublic | null>(null)
const loading = ref(true)
const groups = ref<string[]>([])
const groupsLoading = ref(false)

const initials = computed(() => {
  const name = user.value?.full_name ?? ''
  return name.split(' ').slice(0, 2).map((w: string) => w[0]).join('').toUpperCase()
})

onMounted(async () => {
  const userId = route.params.id as string
  try {
    user.value = await fetchUserById(userId)
  } catch {
    user.value = null
  } finally {
    loading.value = false
  }

  if (user.value && auth.isAdmin) {
    groupsLoading.value = true
    try {
      const res = await adminFetchUserKeycloakGroups(userId)
      groups.value = res.groups ?? []
    } catch {
      groups.value = []
    } finally {
      groupsLoading.value = false
    }
  }
})
</script>

<style scoped>
.upv-wrap {
  max-width: 800px;
  margin: 0 auto;
}

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
.profile-hero__bg svg { width: 100%; height: 100%; }
.profile-hero__inner {
  position: relative;
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 28px 32px;
}
.profile-avatar-wrap { position: relative; flex-shrink: 0; }
.profile-avatar {
  border: 3px solid rgba(255, 255, 255, 0.85);
  box-shadow: var(--shadow-md);
}
.profile-hero__info { flex: 1; min-width: 0; }
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
.profile-hero__dot { margin: 0 6px; opacity: 0.6; }
.profile-hero__badges { display: flex; flex-wrap: wrap; gap: 8px; }

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

.upv-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 20px;
}
.profile-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 22px 24px;
  box-shadow: var(--shadow-sm);
}
.profile-card__head { margin-bottom: 16px; }
.profile-card__title {
  margin: 0;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--color-text-muted);
}
.info-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin: 0;
}
.info-row {
  display: grid;
  grid-template-columns: 140px 1fr;
  gap: 12px;
  align-items: baseline;
  padding-bottom: 10px;
  border-bottom: 1px dashed var(--color-border);
}
.info-row:last-child { border-bottom: none; padding-bottom: 0; }
.info-row dt {
  font-size: 12px;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-weight: 600;
}
.info-row dd {
  margin: 0;
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text);
  word-break: break-word;
}

.upv-groups {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.upv-group-tag {
  font-family: var(--font-mono, monospace);
  font-size: 12px;
}
.upv-groups-empty {
  font-size: 13px;
  color: var(--color-text-muted);
}
.upv-groups-loading {
  display: flex;
  justify-content: flex-start;
  padding: 4px 0;
}

.upv-notfound {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 300px;
}

@media (max-width: 640px) {
  .profile-hero__inner { flex-direction: column; align-items: flex-start; padding: 22px; }
  .profile-hero__name { font-size: 22px; }
  .info-row { grid-template-columns: 1fr; gap: 2px; }
}
</style>
