<template>
  <div class="page learning-page">
    <header class="page-header">
      <div>
        <h1 class="page-title">
          {{ t('learning.page.title') }}
        </h1>
        <p class="page-subtitle">
          {{ t('learning.page.subtitle') }}
        </p>
      </div>
      <n-checkbox
        v-if="hasCompleted"
        v-model:checked="hideCompleted"
        class="hide-completed"
      >
        {{ t('learning.page.hideCompleted') }}
      </n-checkbox>
    </header>

    <n-spin :show="query.isLoading.value">
      <!-- Ошибка сети/5xx ≠ «нет курсов»: явный error-state с повтором -->
      <n-alert
        v-if="query.isError.value"
        type="error"
        :show-icon="true"
        class="error"
      >
        {{ t('learning.page.error') }}
        <n-button
          size="small"
          style="margin-left: 12px"
          @click="query.refetch()"
        >
          {{ t('learning.page.retry') }}
        </n-button>
      </n-alert>
      <n-empty
        v-else-if="!query.isLoading.value && visibleCourses.length === 0"
        :description="t('learning.page.empty')"
        class="empty"
      />
      <div
        v-else
        class="course-blocks"
      >
        <section
          v-for="block in blocks"
          :key="block.title ?? '__other'"
          class="course-block"
        >
          <h2
            v-if="block.title || blocks.length > 1"
            class="course-block__title"
          >
            {{ block.title ?? t('learning.page.otherCourses') }}
          </h2>
          <div class="course-grid">
            <component
              :is="RouterLink"
              v-for="c in block.courses"
              :key="c.id"
              :to="{ name: 'learning-course', params: { slug: c.slug } }"
              class="course-card"
              :class="{ 'course-card--done': completed(c) }"
            >
              <img
                v-if="c.cover_url"
                :src="c.cover_url"
                class="course-card__cover"
                :alt="c.title"
              >
              <div class="course-card__head">
                <span class="course-card__title">{{ c.title }}</span>
                <n-tag
                  size="small"
                  :type="completed(c) ? 'success' : 'default'"
                  :bordered="false"
                >
                  {{ completed(c) ? t('learning.page.done') : t('learning.page.inProgress') }}
                </n-tag>
              </div>
              <p
                v-if="c.description"
                class="course-card__desc"
              >
                {{ excerpt(c.description) }}
              </p>
              <n-progress
                type="line"
                :percentage="percent(c)"
                :height="8"
                :show-indicator="false"
                :aria-label="t('learning.page.progress', { done: c.progress_completed, total: c.progress_total })"
              />
              <span class="course-card__count">
                {{ t('learning.page.progress', { done: c.progress_completed, total: c.progress_total }) }}
              </span>
              <span
                v-if="c.deadline_at"
                class="course-card__deadline"
              >
                {{ t('learning.page.deadline', { date: formatDate(c.deadline_at, locale) }) }}
              </span>
            </component>
          </div>
        </section>
      </div>
    </n-spin>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import { NAlert, NButton, NCheckbox, NEmpty, NProgress, NSpin, NTag } from 'naive-ui'
import { useMyCoursesQuery } from '../../queries/learning'
import { formatDate } from '../../utils/formatDate'
import { richToPlainText } from '../../utils/richText'
import type { MyCourse } from '../../api/learning'

const { t, locale } = useI18n()
const query = useMyCoursesQuery()
const courses = computed<MyCourse[]>(() => query.data.value ?? [])

function completed(c: MyCourse): boolean {
  return c.progress_total > 0 && c.progress_completed >= c.progress_total
}

// Пройденные курсы не должны мешать текущим: по умолчанию они уходят в конец
// блока и приглушаются, чекбоксом их можно скрыть совсем (прод-запрос
// 2026-09-03). Выбор запоминается в localStorage.
const HIDE_COMPLETED_KEY = 'learning.hideCompleted'
const hideCompleted = ref(readStoredFlag())
watch(hideCompleted, (v) => {
  try {
    localStorage.setItem(HIDE_COMPLETED_KEY, v ? '1' : '0')
  } catch {
    /* приватный режим — состояние просто не сохранится */
  }
})

function readStoredFlag(): boolean {
  try {
    return localStorage.getItem(HIDE_COMPLETED_KEY) === '1'
  } catch {
    return false
  }
}

const hasCompleted = computed(() => courses.value.some(completed))
const visibleCourses = computed(() =>
  hideCompleted.value ? courses.value.filter((c) => !completed(c)) : courses.value,
)

interface CourseBlock {
  title: string | null
  courses: MyCourse[]
}

// Группировка по категориям справочника (миграция 109): порядок блоков —
// sort_order категории, курсы без категории — блок «Другие курсы» в конце.
// Внутри блока непройденные курсы идут первыми (прод-запрос 2026-09-03).
const blocks = computed<CourseBlock[]>(() => {
  const named = new Map<string, { sort: number; courses: MyCourse[] }>()
  const other: MyCourse[] = []
  for (const c of visibleCourses.value) {
    if (c.category_title) {
      const g = named.get(c.category_title) ?? {
        sort: c.category_sort ?? Number.MAX_SAFE_INTEGER,
        courses: [],
      }
      g.courses.push(c)
      named.set(c.category_title, g)
    } else {
      other.push(c)
    }
  }
  const groups: CourseBlock[] = [...named.entries()]
    .sort((a, b) => a[1].sort - b[1].sort)
    .map(([title, g]) => ({ title, courses: activeFirst(g.courses) }))
  if (other.length) groups.push({ title: null, courses: activeFirst(other) })
  return groups
})

function activeFirst(list: MyCourse[]): MyCourse[] {
  const active: MyCourse[] = []
  const done: MyCourse[] = []
  for (const c of list) (completed(c) ? done : active).push(c)
  return [...active, ...done]
}

// Описание — rich-text (Markdown): в превью отдаём чистый текст, иначе
// сырые `&nbsp;`/`**` лезут в карточку (прод-кейс 2026-09-03).
function excerpt(raw: string): string {
  return richToPlainText(raw)
}

function percent(c: MyCourse): number {
  if (c.progress_total === 0) return 0
  return Math.round((c.progress_completed * 100) / c.progress_total)
}
</script>

<style scoped>
.page-header {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 8px 16px;
  margin-bottom: 16px;
}

.hide-completed {
  flex-shrink: 0;
  padding-bottom: 2px;
}

.page-title {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
}

.page-subtitle {
  margin: 4px 0 0;
  color: var(--text-secondary, #888);
}

.empty {
  margin: 48px 0;
}

.course-block {
  margin-bottom: 22px;
}

.course-block__title {
  margin: 0 0 10px;
  font-size: 13px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--color-text-muted);
}

.course-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
}

.course-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 16px;
  border: 1px solid var(--border-color, #e5e5e5);
  border-radius: 12px;
  color: inherit;
  text-decoration: none;
  transition:
    box-shadow 0.15s ease,
    opacity 0.15s ease;
}

.course-card:hover {
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
}

/* Пройденный курс — «погашен» визуально (прод-запрос 2026-09-03), но
   приглушается только декор (обложка/прогресс) + пунктирная рамка.
   Opacity на карточку целиком запрещён: цветной текст выцветает ниже
   контраста WCAG AA 4.5:1 (даже чёрный при 0.55 даёт ~4.0) — это ловит
   Axe-гейт learn-visual (2.49:1 на course-card__count, CI 2026-09-03). */
.course-card--done {
  border-style: dashed;
}

.course-card--done .course-card__cover,
.course-card--done :deep(.n-progress) {
  opacity: 0.55;
}

.course-card--done .course-card__cover {
  filter: grayscale(0.4);
}

.course-card--done:hover .course-card__cover,
.course-card--done:hover :deep(.n-progress) {
  opacity: 1;
  filter: none;
}

.course-card__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.course-card__cover {
  width: 100%;
  height: 150px;
  object-fit: cover;
  border-radius: 8px;
  display: block;
}

.course-card__title {
  font-weight: 600;
  line-height: 1.35;
}

.course-card__desc {
  margin: 0;
  color: var(--text-secondary, #888);
  font-size: 13px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* Единообразие ряда карточек (прод-запрос 2026-09-03): сетка растягивает
   карточки по высоте строки, нижний блок (прогресс/счётчик/дедлайн)
   прижат к низу — ряды прогресса на соседних карточках совпадают,
   как в learn-теме (.n-progress { margin-top: auto }). */
.course-card :deep(.n-progress) {
  margin-top: auto;
  padding-top: 6px;
}

.course-card__count {
  font-size: 12px;
  color: var(--text-secondary, #999);
}

.course-card__deadline {
  font-size: 12px;
  color: #d5483c;
}
</style>
