<template>
  <section
    v-if="birthdays.length"
    class="widget"
  >
    <div class="widget__header">
      <h3 class="widget__title">
        {{ t('home.birthdays.title') }}
      </h3>
      <n-button
        v-if="birthdays.length > VISIBLE_LIMIT"
        text
        size="tiny"
        @click="router.push('/staff')"
      >
        {{ t('home.showAll') }}
      </n-button>
    </div>

    <!-- Список (ТЗ п.8): каждый именинник — отдельная строка.
         Аватар + ФИО + дата. Без карусели/paging/dots. -->
    <ul class="birthday-list">
      <li
        v-for="b in visible"
        :key="b.id"
        class="birthday-row"
      >
        <button
          type="button"
          class="birthday-row__btn"
          @click="openProfile(b.id)"
        >
          <UserAvatar
            :user="b"
            :size="36"
            class="birthday-row__avatar"
          />
          <span class="birthday-row__name">{{ displayName(b.full_name) }}</span>
          <span class="birthday-row__date">{{ formatDate(b.birth_date) }}</span>
        </button>
      </li>
    </ul>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton } from 'naive-ui'
import { useRouter } from 'vue-router'
import { useBirthdaysQuery } from '../../queries/users'
import UserAvatar from '../UserAvatar.vue'

const { t, locale } = useI18n()
const router = useRouter()

// Лимит строк в виджете; остальных показывает «Показать все» → /staff.
const VISIBLE_LIMIT = 6

const { data } = useBirthdaysQuery()
const birthdays = computed(() => data.value?.items ?? [])
const visible = computed(() => birthdays.value.slice(0, VISIBLE_LIMIT))

// «День + месяц» в текущей локали (ru: «5 марта», en: «March 5»).
function formatDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00`)
  return new Intl.DateTimeFormat(locale.value, { day: 'numeric', month: 'long' }).format(d)
}

// Фамилия + имя без отчества: первые 2 слова.
function displayName(fullName: string): string {
  return fullName.trim().split(/\s+/).slice(0, 2).join(' ')
}

function openProfile(id: string): void {
  router.push(`/users/${id}`)
}
</script>

<style scoped>
.widget {
  background: var(--color-mage-card, var(--color-surface));
  border: 1px solid var(--color-mage-border, var(--color-border));
  border-radius: var(--radius-card, var(--radius-lg));
  padding: var(--space-card-inner, 16px) var(--space-card-inner, 18px) calc(var(--space-card-inner, 16px) - 4px);
  box-shadow: var(--shadow-soft, var(--shadow-sm));
}
.widget__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}
.widget__title {
  margin: 0;
  font-size: 13px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--color-text-muted);
}

/* Список именинников: каждая запись — отдельная строка (ТЗ п.8) */
.birthday-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
}
.birthday-row + .birthday-row {
  border-top: 1px solid var(--color-mage-border, var(--color-border));
}
.birthday-row__btn {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 10px 4px;
  background: transparent;
  border: none;
  cursor: pointer;
  text-align: left;
  font: inherit;
  color: inherit;
  transition: background var(--t-fast);
  border-radius: var(--radius-sm);
}
.birthday-row__btn:hover {
  background: color-mix(in srgb, var(--color-mage-secondary, #2f6cb5) 6%, transparent);
}
.birthday-row__avatar {
  flex-shrink: 0;
}
.birthday-row__name {
  flex: 1;
  min-width: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-mage-text, var(--color-text));
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.birthday-row__date {
  flex-shrink: 0;
  font-size: 12px;
  color: var(--color-mage-text-secondary, var(--color-text-muted));
}
</style>
