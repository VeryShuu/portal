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

    <div class="birthdays-row">
      <article
        v-for="(b, i) in birthdays"
        :key="`${b.full_name}-${i}`"
        class="birthday-card"
      >
        <n-avatar
          round
          :size="48"
          :src="b.avatar_url ?? undefined"
          class="birthday-card__avatar"
        >
          {{ initials(b.full_name) }}
        </n-avatar>
        <div class="birthday-card__body">
          <span class="birthday-card__name">{{ b.full_name }}</span>
          <span class="birthday-card__date">{{ formatDate(b.birth_date) }}</span>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NAvatar } from 'naive-ui'
import { useBirthdaysQuery } from '../../queries/users'

const { t, locale } = useI18n()

const { data } = useBirthdaysQuery()
const birthdays = computed(() => data.value?.items ?? [])

// «День + месяц» в текущей локали (ru: «5 марта», en: «March 5»).
// Год берём из недели (текущий), чтобы дата в «день недели» попадала корректно —
// но показываем только день и название месяца. 'T00:00:00' фиксит timezone-сдвиг.
function formatDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00`)
  return new Intl.DateTimeFormat(locale.value, { day: 'numeric', month: 'long' }).format(d)
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

/* Горизонтальный ряд карточек; на узком экране переносятся. */
.birthdays-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.birthday-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  background: var(--color-bg, #fff);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  min-width: 0;
}

.birthday-card__avatar {
  flex-shrink: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text-muted);
}

.birthday-card__body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.birthday-card__name {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.birthday-card__date {
  font-size: 12px;
  color: var(--color-text-secondary, #666);
}
</style>
