<template>
  <section
    v-if="birthdays.length"
    class="widget"
  >
    <div class="widget__header">
      <h3 class="widget__title">
        {{ t('home.birthdays.title') }}
      </h3>
    </div>

    <ul class="birthdays-list">
      <li
        v-for="(b, i) in birthdays"
        :key="`${b.full_name}-${i}`"
        class="birthday-row"
      >
        <n-avatar
          round
          :size="36"
          :src="b.avatar_url ?? undefined"
          class="birthday-row__avatar"
        >
          {{ initials(b.full_name) }}
        </n-avatar>
        <span class="birthday-row__name">{{ b.full_name }}</span>
        <span class="birthday-row__day">{{ dayOfMonth(b.birth_date) }}</span>
      </li>
    </ul>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NAvatar } from 'naive-ui'
import { useBirthdaysQuery } from '../../queries/users'

const { t } = useI18n()

const { data } = useBirthdaysQuery()
const birthdays = computed(() => data.value?.items ?? [])

// День месяца из ISO-даты рождения (год/месяц не показываем по ТЗ).
// 'T00:00:00' — фиксит timezone-сдвиг (иначе в UTC− может стать предыдущим днём).
function dayOfMonth(iso: string): number {
  return new Date(`${iso}T00:00:00`).getDate()
}

// Фоллбэк аватара: инициалы из первых букв слов ФИО (до 2 символов).
function initials(fullName: string): string {
  return fullName
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w.charAt(0).toUpperCase())
    .join('')
}
</script>

<style scoped>
.widget {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 16px 18px 12px;
  box-shadow: var(--shadow-sm);
}
.widget__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.widget__title {
  margin: 0;
  font-size: 13px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--color-text-muted);
}

.birthdays-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
}

.birthday-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
  border-bottom: 1px solid var(--color-border);
}
.birthday-row:last-child {
  border-bottom: none;
}

.birthday-row__avatar {
  flex-shrink: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-muted);
}

.birthday-row__name {
  flex: 1 1 auto;
  min-width: 0;
  font-size: 14px;
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.birthday-row__day {
  flex-shrink: 0;
  margin-left: auto;
  font-size: 15px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--color-brand-red, #d92e2e);
  min-width: 28px;
  text-align: right;
}
</style>
