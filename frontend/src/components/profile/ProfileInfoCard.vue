<template>
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
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { UserPublic } from '../../api/users'
import type { UserMe } from '../../api/auth'

type DisplayUser = UserMe | UserPublic

defineProps<{
  user: DisplayUser
  isOwn: boolean
  extraAttributes: Array<{ key: string; label: string; value: string }>
}>()

const { t } = useI18n()
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
@media (max-width: 960px) {
  .info-row { grid-template-columns: 1fr; gap: 2px; }
}
</style>
