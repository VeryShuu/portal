<template>
  <div class="profile-wrap" :class="{ 'profile-wrap--view': !isOwn }">
    <n-spin v-if="loading" style="margin: 60px auto; display: block" />

    <template v-else-if="user">
      <section class="profile-hero">
        <div class="profile-hero__bg" aria-hidden="true">
          <svg viewBox="0 0 1200 300" preserveAspectRatio="xMidYMid slice">
            <defs>
              <linearGradient id="profile-wave" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stop-color="#4a90c4" stop-opacity="0.22" />
                <stop offset="100%" stop-color="#143a66" stop-opacity="0.05" />
              </linearGradient>
            </defs>
            <path fill="url(#profile-wave)" d="M0,200 C200,260 420,160 620,200 C820,240 1020,280 1200,220 L1200,300 L0,300 Z" />
            <path fill="rgba(255,255,255,0.06)" d="M0,240 C220,280 440,220 660,240 C880,260 1080,300 1200,260 L1200,300 L0,300 Z" />
          </svg>
        </div>

        <div class="profile-hero__inner">
          <div class="profile-avatar-wrap">
            <n-avatar round :size="96" :src="user.avatar_url ?? undefined" class="profile-avatar">
              <template v-if="!user.avatar_url">{{ initials }}</template>
            </n-avatar>
            <n-upload
              v-if="isOwn"
              accept="image/jpeg,image/png,image/webp"
              :show-file-list="false"
              :custom-request="handleAvatarUpload"
              class="avatar-upload"
            >
              <button type="button" class="avatar-edit" :aria-label="t('users.profile.changeAvatar')">
                <n-icon size="16"><CameraOutline /></n-icon>
              </button>
            </n-upload>
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

      <div class="profile-grid" :class="{ 'profile-grid--view': !isOwn }">
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
            <template v-if="!isOwn">
              <div v-for="row in extraAttributes" :key="row.key" class="info-row">
                <dt>{{ row.label }}</dt>
                <dd>{{ row.value }}</dd>
              </div>
            </template>
            <div class="info-row">
              <dt>{{ t('users.fields.lastLoginAt') }}</dt>
              <dd>{{ user.last_login_at ? new Date(user.last_login_at).toLocaleString() : '—' }}</dd>
            </div>
          </dl>
        </section>

        <section v-if="auth.isAdmin" class="profile-card">
          <header class="profile-card__head">
            <h2 class="profile-card__title">{{ t('users.profile.sections.groups') }}</h2>
          </header>
          <div v-if="groupsLoading" class="groups-loading">
            <n-spin size="small" />
          </div>
          <div v-else-if="groups.length" class="groups-list">
            <n-tag
              v-for="g in groups"
              :key="g"
              size="medium"
              :bordered="false"
              class="group-tag"
            >
              {{ g }}
            </n-tag>
          </div>
          <div v-else class="groups-empty">
            {{ t('users.profile.noGroups') }}
          </div>
        </section>

        <section v-if="isOwn" class="profile-card">
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

        <section v-if="isOwn && auth.isLocalUser" class="profile-card profile-card--wide">
          <header class="profile-card__head">
            <h2 class="profile-card__title">{{ t('users.password.changeTitle') }}</h2>
          </header>
          <n-alert v-if="passwordError" type="error" closable @close="passwordError = null" style="margin-bottom: 12px">
            {{ passwordError }}
          </n-alert>
          <n-alert v-if="passwordSuccess" type="success" closable @close="passwordSuccess = false" style="margin-bottom: 12px">
            {{ t('users.password.changed') }}
          </n-alert>
          <n-form :model="passwordForm" label-placement="top" class="password-form">
            <n-form-item :label="t('users.password.current')">
              <n-input
                v-model:value="passwordForm.current"
                type="password"
                show-password-on="click"
                :input-props="{ autocomplete: 'current-password' }"
              />
            </n-form-item>
            <n-form-item :label="t('users.password.new')">
              <n-input
                v-model:value="passwordForm.next"
                type="password"
                show-password-on="click"
                :input-props="{ autocomplete: 'new-password' }"
              />
            </n-form-item>
            <n-form-item :label="t('users.password.confirm')">
              <n-input
                v-model:value="passwordForm.confirm"
                type="password"
                show-password-on="click"
                :input-props="{ autocomplete: 'new-password' }"
              />
            </n-form-item>
          </n-form>
          <div class="card-actions">
            <n-button type="primary" :loading="passwordSaving" :disabled="!canChangePassword" @click="savePassword">
              {{ t('users.password.save') }}
            </n-button>
          </div>
        </section>
        <DepartmentColleagues
          v-if="user.department"
          :department="user.department"
          :exclude-user-id="user.id"
        />
      </div>
    </template>

    <div v-else class="profile-notfound">
      <n-result status="404" :title="t('users.notFound')" :description="t('errors.notFound.description')">
        <template #footer>
          <n-button @click="router.back()">{{ t('common.back') }}</n-button>
        </template>
      </n-result>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import {
  NAvatar, NUpload, NButton, NIcon, NSpin, NResult, NTag,
  NForm, NFormItem, NSelect, NSwitch, NInput, NAlert,
  useMessage, type UploadCustomRequestOptions,
} from 'naive-ui'
import { CameraOutline, ShieldOutline, KeyOutline } from '@vicons/ionicons5'
import { useAuthStore } from '../stores/auth'
import {
  fetchUserById, patchMyProfile, uploadAvatar, adminFetchUserKeycloakGroups,
  type UserPublic,
} from '../api/users'
import type { UserMe } from '../api/auth'
import { fetchAttributeSchema, type UserAttributeMappingSchema } from '../api/userAttributeMappings'
import { changePassword } from '../api/auth'
import DepartmentColleagues from '../components/profile/DepartmentColleagues.vue'

// Общий тип для отображения: UserMe и UserPublic совпадают по всем полям, которые
// рендерятся в шаблоне (id, full_name, email, phone, department, position, avatar_url,
// presence_status, last_login_at). Поле `attributes` есть только у UserPublic — доступ
// к нему гейтится `v-if="!isOwn"` и компьютедом extraAttributes.
type DisplayUser = UserMe | UserPublic

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const auth = useAuthStore()
const message = useMessage()

const isOwn = computed(() => route.name === 'profile')

const fetchedUser = ref<UserPublic | null>(null)
const loading = ref(false)
const attrSchema = ref<UserAttributeMappingSchema[]>([])
const groups = ref<string[]>([])
const groupsLoading = ref(false)

const user = computed<DisplayUser | null>(() =>
  isOwn.value ? auth.user : fetchedUser.value
)

const initials = computed(() => {
  const name = user.value?.full_name ?? ''
  return name.split(' ').slice(0, 2).map((w: string) => w[0]).join('').toUpperCase()
})

const extraAttributes = computed(() => {
  const attrs = fetchedUser.value?.attributes ?? {}
  const lang = fetchedUser.value?.lang ?? 'ru'
  const rows: Array<{ key: string; label: string; value: string }> = []
  for (const item of attrSchema.value) {
    const raw = attrs[item.attr_key]
    if (raw === undefined || raw === null || raw === '') continue
    const value = Array.isArray(raw) ? raw.filter(Boolean).join(', ') : String(raw)
    if (!value) continue
    const label = (lang === 'en' && item.label_en) ? item.label_en : item.label_ru
    rows.push({ key: item.attr_key, label, value })
  }
  return rows
})

const form = ref({
  presence_status: auth.user?.presence_status ?? 'office' as 'office' | 'remote' | 'vacation',
  notify_email: auth.user?.notify_email ?? true,
  notify_inapp: auth.user?.notify_inapp ?? true,
})

const saving = ref(false)
const passwordForm = ref({ current: '', next: '', confirm: '' })
const passwordSaving = ref(false)
const passwordError = ref<string | null>(null)
const passwordSuccess = ref(false)

const roleLabel = computed(() => {
  if (!auth.user) return ''
  if (auth.user.role === 'admin') return t('admin.users.role.admin')
  if (auth.user.role === 'editor') return t('admin.users.role.editor')
  return t('admin.users.role.reader')
})

const authSourceLabel = computed(() =>
  auth.isLocalUser ? t('users.profile.authSource.local') : t('users.profile.authSource.keycloak')
)

const statusOptions = computed(() => [
  { label: t('users.profile.status.office'), value: 'office' },
  { label: t('users.profile.status.remote'), value: 'remote' },
  { label: t('users.profile.status.vacation'), value: 'vacation' },
])

const canChangePassword = computed(() =>
  passwordForm.value.current.length > 0 &&
  passwordForm.value.next.length >= 8 &&
  passwordForm.value.next === passwordForm.value.confirm
)

watch(() => auth.user, (u) => {
  if (isOwn.value && u) {
    form.value.presence_status = u.presence_status
    form.value.notify_email = u.notify_email
    form.value.notify_inapp = u.notify_inapp
  }
})

async function loadGroups(userId: string) {
  if (!auth.isAdmin) return
  groupsLoading.value = true
  groups.value = []
  try {
    const res = await adminFetchUserKeycloakGroups(userId)
    groups.value = res.groups ?? []
  } catch {
    groups.value = []
  } finally {
    groupsLoading.value = false
  }
}

async function ensureAttrSchema() {
  if (attrSchema.value.length > 0) return
  try {
    const schema = await fetchAttributeSchema()
    attrSchema.value = schema.items ?? []
  } catch {
    attrSchema.value = []
  }
}

async function loadData() {
  groups.value = []
  await ensureAttrSchema()
  if (isOwn.value) {
    fetchedUser.value = null
    loading.value = false
    if (auth.user) await loadGroups(auth.user.id)
    return
  }
  const userId = route.params.id as string
  loading.value = true
  fetchedUser.value = null
  try {
    fetchedUser.value = await fetchUserById(userId)
  } catch {
    fetchedUser.value = null
  } finally {
    loading.value = false
  }
  if (fetchedUser.value) await loadGroups(userId)
}

onMounted(loadData)
watch(() => route.params.id, loadData)

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

async function handleAvatarUpload({ file, onFinish, onError }: UploadCustomRequestOptions) {
  try {
    const updated = await uploadAvatar(file.file as File)
    auth.setUser(updated)
    message.success(t('users.profile.changeAvatar'))
    onFinish()
  } catch {
    message.error(t('errors.generic'))
    onError()
  }
}

async function savePassword() {
  passwordError.value = null
  passwordSuccess.value = false
  if (passwordForm.value.next !== passwordForm.value.confirm) {
    passwordError.value = t('users.password.mismatch')
    return
  }
  passwordSaving.value = true
  try {
    await changePassword(passwordForm.value.current, passwordForm.value.next)
    passwordSuccess.value = true
    passwordForm.value = { current: '', next: '', confirm: '' }
  } catch (err: unknown) {
    const e = err as { status?: number }
    if (e?.status === 401) {
      passwordError.value = t('users.password.wrongCurrent')
    } else {
      passwordError.value = t('errors.generic')
    }
  } finally {
    passwordSaving.value = false
  }
}
</script>

<style scoped>
.profile-wrap {
  max-width: 1200px;
  margin: 0 auto;
}
.profile-wrap--view {
  max-width: 800px;
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

.profile-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}
.profile-grid--view {
  grid-template-columns: 1fr;
}

.profile-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 22px 24px;
  box-shadow: var(--shadow-sm);
}
.profile-card--wide {
  grid-column: 1 / -1;
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
.info-row:last-child {
  border-bottom: none;
  padding-bottom: 0;
}
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

.groups-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.group-tag {
  font-family: var(--font-mono, monospace);
  font-size: 12px;
}
.groups-empty {
  font-size: 13px;
  color: var(--color-text-muted);
}
.groups-loading {
  display: flex;
  justify-content: flex-start;
  padding: 4px 0;
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

.password-form {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
}

.profile-notfound {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 300px;
}

@media (max-width: 960px) {
  .profile-grid { grid-template-columns: 1fr; }
  .password-form { grid-template-columns: 1fr; gap: 0; }
  .info-row { grid-template-columns: 1fr; gap: 2px; }
}
@media (max-width: 640px) {
  .profile-hero__inner { flex-direction: column; align-items: flex-start; padding: 22px; }
  .profile-hero__name { font-size: 22px; }
}
</style>
