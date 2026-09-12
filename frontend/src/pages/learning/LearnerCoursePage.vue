<template>
  <div class="page learner-course">
    <img
      v-if="course?.cover_url"
      :src="course.cover_url"
      class="course-cover"
      :alt="course.title"
    >
    <header class="course-header">
      <h1 class="course-title">
        {{ course?.title ?? t('common.loading') }}
      </h1>
      <div
        v-if="course"
        class="course-summary"
      >
        <div class="course-progress-label">
          <span class="course-count">
            {{ t('learning.page.progress', { done: course.progress_completed, total: course.progress_total }) }}
          </span>
          <span
            class="course-percentage"
            :class="{ 'course-percentage--done': courseComplete }"
          >{{ percent }}%</span>
        </div>
        <n-progress
          type="line"
          :percentage="percent"
          :height="8"
          :status="courseComplete ? 'success' : 'default'"
          class="course-progress"
          :show-indicator="false"
          :aria-label="t('learning.page.progress', { done: course.progress_completed, total: course.progress_total })"
        />
        <span
          v-if="course.deadline_at"
          class="course-deadline"
        >
          {{ t('learning.page.deadline', { date: formatDate(course.deadline_at, locale) }) }}
        </span>
        <n-button
          v-if="courseComplete"
          tag="a"
          :href="certificateFileUrl(slug)"
          size="small"
        >
          {{ t('learning.course.certificate') }}
        </n-button>
      </div>
    </header>

    <!-- Ревью 2026-08-30: ошибка ≠ «Загрузка…» навсегда. Явный error-state
         с повтором — как на списке курсов (learning.page.error). -->
    <n-alert
      v-if="query.isError.value"
      type="error"
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

    <n-spin :show="query.isLoading.value">
      <div
        v-if="course"
        class="course-workspace"
        :class="{ 'course-workspace--with-description': hasDescription }"
      >
        <section
          v-if="hasDescription"
          class="course-introduction"
          aria-labelledby="course-introduction-title"
        >
          <h2
            id="course-introduction-title"
            class="course-section-title"
          >
            {{ t('learning.course.about') }}
          </h2>
          <!-- Описание — rich-text (тот же редактор, что у новостей/БЗ):
               Markdown → HTML → DOMPurify (двойная защита, sanitize на записи). -->
          <div
            class="course-description"
            v-html="renderedDescription"
          />
        </section>
        <section
          class="course-programme"
          aria-labelledby="course-programme-title"
        >
          <h2
            id="course-programme-title"
            class="course-section-title"
          >
            {{ t('learning.course.programme') }}
          </h2>
          <n-empty
            v-if="items.length === 0"
            :description="t('learning.course.empty')"
            class="empty"
          />
          <ol
            v-else
            class="items"
          >
            <template
              v-for="item in items"
              :key="item.id"
            >
              <!-- Раздел-заголовок (миграция 110): структура, а не элемент —
                   не нумеруется, не отмечается, прогресс не меняет -->
              <li
                v-if="item.type === 'section'"
                class="items__section"
              >
                {{ item.title }}
              </li>
              <LearnerCourseItemCard
                v-else
                :item="item"
                :index="(gradedNumbers.get(item.id) ?? 1) - 1"
                :origins="origins"
                :completing="completeMut.isPending.value"
                @complete="complete"
                @open-test="openTest"
              />
            </template>
          </ol>
        </section>
      </div>
    </n-spin>
    <LearnerTestPanel
      v-if="testItem"
      :key="testItem.id"
      :item="testItem"
      :slug="slug"
      @close="testItem = null"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  NAlert,
  NButton,
  NEmpty,
  NProgress,
  NSpin,
} from 'naive-ui'
import { useMyCourseQuery, useCompleteMaterialMutation, useVideoOriginsQuery } from '../../queries/learning'
import { certificateFileUrl, type MyCourseItem } from '../../api/learning'
import { formatDate } from '../../utils/formatDate'
import { parseApiError } from '../../utils/parseApiError'
import { mdUnsafe as md } from '../../utils/markdown'
import { sanitizeHtmlAllowIframe } from '../../utils/sanitize'
import { useMessage } from 'naive-ui'
import LearnerTestPanel from '../../components/learning/LearnerTestPanel.vue'
import LearnerCourseItemCard from '../../components/learning/LearnerCourseItemCard.vue'

const route = useRoute()
const { t, locale } = useI18n()
const message = useMessage()

const slug = computed(() => String(route.params.slug ?? ''))
const query = useMyCourseQuery(slug)
const course = computed(() => query.data.value ?? null)
const items = computed<MyCourseItem[]>(() => course.value?.items ?? [])
// сквозная нумерация оцениваемых элементов (разделы не нумеруются)
const gradedNumbers = computed(() => {
  const map = new Map<string, number>()
  let n = 0
  for (const it of items.value) {
    if (it.type === 'section') continue
    n += 1
    map.set(it.id, n)
  }
  return map
})
const hasDescription = computed(() => !!course.value?.description?.trim())

// Разрешённые iframe-origin'ы из настройки (Admin UI → System); единый
// источник для обоих контуров — /learning/meta (learn-сборка без bootstrap).
const { origins } = useVideoOriginsQuery()

// rich-описание: тот же конвейер, что у новостей — Markdown → HTML →
// DOMPurify с iframe-гейтом (на записи бэкенд уже прогнал nh3).
const renderedDescription = computed(() => {
  const raw = course.value?.description
  if (!raw) return ''
  return sanitizeHtmlAllowIframe(md.render(raw), origins.value)
})

const percent = computed(() => {
  const c = course.value
  if (!c || c.progress_total === 0) return 0
  return Math.round((c.progress_completed * 100) / c.progress_total)
})

// Курс пройден полностью → доступен сертификат (ленивая выдача: первый
// переход по ссылке генерирует PDF, повторные отдают сохранённый).
const courseComplete = computed(
  () =>
    !!course.value &&
    course.value.progress_total > 0 &&
    course.value.progress_completed >= course.value.progress_total,
)
const completeMut = useCompleteMaterialMutation()

async function complete(item: MyCourseItem) {
  try {
    await completeMut.mutateAsync({ itemId: item.id, slug: slug.value })
    message.success(t('learning.course.markedDone'))
  } catch (e) {
    message.error(parseApiError(e, t))
  }
}

const testItem = ref<MyCourseItem | null>(null)

function openTest(item: MyCourseItem) {
  testItem.value = item
}
</script>

<style scoped>
.learner-course {
  max-width: var(--content-standard);
  margin-inline: auto;
}

.course-cover {
  display: block;
  width: 100%;
  height: clamp(220px, 28vw, 360px);
  object-fit: cover;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  margin-bottom: 28px;
}

.course-header {
  display: grid;
  gap: 24px;
  margin-bottom: 32px;
  padding-bottom: 28px;
  border-bottom: 1px solid var(--color-border);
}

.course-title {
  margin: 0;
  color: var(--color-text);
  font-size: clamp(26px, 3vw, 36px);
  font-weight: 750;
  line-height: 1.2;
  letter-spacing: -0.025em;
  overflow-wrap: anywhere;
}

.course-summary {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 10px;
}

.course-progress-label {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.course-progress {
  width: 100%;
}

.course-count {
  color: var(--color-text-muted);
  font-size: 13px;
}

.course-percentage {
  color: var(--color-text);
  font-size: 16px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.course-percentage--done {
  color: color-mix(in srgb, var(--color-success) 45%, var(--color-text));
}

.course-deadline {
  font-size: 13px;
  color: var(--color-text-muted);
}

.course-workspace {
  display: grid;
  align-items: start;
  gap: 32px;
}

.course-programme,
.course-introduction {
  min-width: 0;
}

.course-section-title {
  margin: 0 0 20px;
  color: var(--color-text);
  font-size: 20px;
  font-weight: 650;
  line-height: 1.4;
}

.course-description {
  color: var(--color-text);
  font-size: 15px;
  line-height: 1.85;
  overflow-wrap: anywhere;
}

.course-description :deep(p) {
  margin: 0 0 14px;
}

.course-description :deep(p:last-child) {
  margin-bottom: 0;
}

.course-description :deep(h2),
.course-description :deep(h3),
.course-description :deep(h4) {
  margin: 22px 0 10px;
  color: var(--color-text);
  font-weight: 650;
  line-height: 1.4;
}

.course-description :deep(h2) { font-size: 18px; }
.course-description :deep(h3),
.course-description :deep(h4) { font-size: 16px; }

.course-description :deep(ul),
.course-description :deep(ol) {
  margin: 0 0 14px;
  padding-left: 22px;
}

.course-description :deep(li) {
  margin-bottom: 6px;
}

.course-description :deep(a) {
  color: var(--color-brand-sky);
}

.course-description :deep(img) {
  max-width: 100%;
  border-radius: var(--radius-md);
}

.course-description :deep(blockquote) {
  margin: 0 0 14px;
  padding-left: 14px;
  border-left: 3px solid var(--color-border-strong);
  color: var(--color-text-muted);
}

.course-description :deep(pre) {
  overflow-x: auto;
  padding: 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-size: 13px;
}

.course-description :deep(table) {
  max-width: 100%;
  border-collapse: collapse;
}

.course-description :deep(td),
.course-description :deep(th) {
  padding: 6px 10px;
  border: 1px solid var(--color-border);
}

.empty {
  margin: 32px 0;
}

.items__section {
  list-style: none;
  margin: 18px 0 6px;
  font-size: 15px;
  font-weight: 700;
  color: var(--color-text);
}
.items__section:first-child {
  margin-top: 0;
}

.items {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 0;
  margin: 0;
  list-style: none;
}

@media (min-width: 1024px) {
  .course-header {
    grid-template-columns: minmax(0, 1fr) minmax(240px, 320px);
    align-items: center;
    gap: 40px;
  }

  /* Описание — левая колонка, программа (материалы/тесты) — правая
     (ревью 2026-08-31). Разделитель — на правой колонке. */
  .course-workspace--with-description {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1.1fr);
    gap: 40px;
  }

  .course-workspace--with-description .course-programme {
    padding-left: 32px;
    border-left: 1px solid var(--color-border);
  }
}
</style>
