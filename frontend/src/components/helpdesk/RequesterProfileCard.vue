<template>
  <n-card
    v-if="profile && hasAnyField"
    class="requester-card"
    size="small"
    :bordered="true"
  >
    <template #header>
      <span class="requester-card__title">{{ t('helpdesk.requesterProfile.title') }}</span>
    </template>

    <div class="requester-card__name">
      {{ profile.full_name }}
    </div>
    <dl class="requester-card__fields">
      <div
        v-for="row in rows"
        :key="row.key"
        class="requester-card__row"
      >
        <dt class="requester-card__label">
          {{ row.label }}
        </dt>
        <dd class="requester-card__value">
          {{ row.value }}
        </dd>
      </div>
    </dl>
  </n-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NCard } from 'naive-ui'
import type { HelpdeskRequesterProfile } from '../../api/helpdesk'

const props = defineProps<{ profile: HelpdeskRequesterProfile | null | undefined }>()
const { t } = useI18n()

interface ProfileRow {
  key: string
  label: string
  value: string
}

const rows = computed<ProfileRow[]>(() => {
  const p = props.profile
  if (!p) return []
  const entries: Array<{ key: string; label: string; value: string | null | undefined }> = [
    { key: 'email', label: t('helpdesk.requesterProfile.email'), value: p.email },
    { key: 'department', label: t('helpdesk.requesterProfile.department'), value: p.department },
    { key: 'position', label: t('helpdesk.requesterProfile.position'), value: p.position },
    { key: 'city', label: t('helpdesk.requesterProfile.city'), value: p.city },
    { key: 'mobile', label: t('helpdesk.requesterProfile.mobilePhone'), value: p.mobile_phone },
    { key: 'internal', label: t('helpdesk.requesterProfile.internalPhone'), value: p.internal_phone },
  ]
  return entries.filter((e) => typeof e.value === 'string' && e.value.trim() !== '') as ProfileRow[]
})

const hasAnyField = computed(() => rows.value.length > 0)
</script>

<style scoped>
/* Sidebar-карточка профиля заявителя (правая колонка, как в OTRS). */
.requester-card__title {
  font-size: 13px;
  font-weight: 600;
}
.requester-card__name {
  font-weight: 600;
  font-size: 15px;
  margin-bottom: 10px;
  word-break: break-word;
}
.requester-card__fields {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.requester-card__row {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.requester-card__label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--color-text-muted);
  font-weight: 600;
  margin: 0;
}
.requester-card__value {
  margin: 0;
  font-size: 13px;
  color: var(--color-text);
  word-break: break-word;
}
</style>
