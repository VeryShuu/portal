<template>
  <section
    v-if="visible"
    class="widget"
  >
    <div class="widget__header">
      <h3 class="widget__title">
        {{ t('learning.widget.title') }}
      </h3>
      <RouterLink
        class="widget__link"
        to="/learning"
      >
        {{ t('learning.widget.viewAll') }}
      </RouterLink>
    </div>

    <div
      v-if="query.isLoading.value"
      class="my-courses__skeleton"
    >
      <div
        v-for="i in 2"
        :key="`sk-${i}`"
        class="my-courses__skeleton-row"
      />
    </div>

    <ul
      v-else-if="activeCourses.length"
      class="my-courses__list"
    >
      <li
        v-for="c in activeCourses"
        :key="c.id"
        class="my-courses__item"
      >
        <RouterLink
          class="my-courses__link"
          :to="{ name: 'learning-course', params: { slug: c.slug } }"
          :title="c.title"
        >
          <div class="my-courses__info">
            <div class="my-courses__title">
              {{ c.title }}
            </div>
            <n-progress
              type="line"
              :percentage="percent(c)"
              :show-indicator="false"
              :height="6"
              class="my-courses__bar"
            />
          </div>
          <span class="my-courses__count">{{ c.progress_completed }}/{{ c.progress_total }}</span>
        </RouterLink>
      </li>
    </ul>

    <n-empty
      v-else
      :description="courses.length ? t('learning.widget.allDone') : t('learning.widget.empty')"
      size="small"
      class="my-courses__empty"
    />
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { NEmpty, NProgress } from 'naive-ui'
import { useModulesStore } from '../../stores/modules'
import { useMyCoursesQuery } from '../../queries/learning'

const { t } = useI18n()
const modulesStore = useModulesStore()

// Виджет показывается всем авторизованным при включённом модуле: список
// «мои курсы» у неподписанного сотрудника просто пуст (сервер фильтрует).
const visible = computed(() => modulesStore.isEnabled('learning'))
const query = useMyCoursesQuery(visible)
const courses = computed(() => query.data.value ?? [])

// Пройденность — та же семантика, что на странице «Обучение» (LearningPage):
// все элементы курса (материалы + тесты) закрыты. Виджет показывает только
// незавершённые; пройденные остаются доступны по ссылке «Все курсы».
const activeCourses = computed(() => courses.value.filter((c) => !completed(c)))

function completed(c: { progress_completed: number; progress_total: number }): boolean {
  return c.progress_total > 0 && c.progress_completed >= c.progress_total
}

function percent(c: { progress_completed: number; progress_total: number }): number {
  if (!c.progress_total) return 0
  return Math.round((c.progress_completed / c.progress_total) * 100)
}
</script>

<style scoped>
/* Рамка виджета — тот же блок, что у соседей по aside (Photos/Meetings/
   QuickServices): стили .widget живут в scoped-стилях каждого виджета. */
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
.widget__link {
  font-size: 12px;
  color: var(--color-brand-red);
  text-decoration: none;
}
.widget__link:hover { text-decoration: underline; }

.my-courses__skeleton {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.my-courses__skeleton-row {
  height: 32px;
  border-radius: 8px;
  background: rgba(128, 128, 128, 0.12);
  animation: pulse 1.4s ease-in-out infinite;
}

@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.6;
  }
}

.my-courses__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.my-courses__item {
  display: flex;
  align-items: center;
  gap: 10px;
}

.my-courses__link {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  /* min-width: 0 — иначе автоматический минимум flex-элемента равен ширине
     nowrap-заголовка, и ellipsis на .my-courses__title не срабатывает. */
  min-width: 0;
  color: inherit;
  text-decoration: none;
}

.my-courses__link:hover .my-courses__title {
  text-decoration: underline;
}

.my-courses__info {
  flex: 1;
  min-width: 0;
}

.my-courses__title {
  font-size: 13px;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.my-courses__bar {
  margin-top: 4px;
}

.my-courses__count {
  font-size: 12px;
  color: var(--text-secondary, #999);
  flex-shrink: 0;
}

.my-courses__empty {
  padding: 8px 0;
}
</style>
