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

    <div class="birthdays-stage">
      <button
        type="button"
        class="nav-arrow"
        :disabled="currentPage === 0"
        :aria-label="t('common.previous')"
        @click="prev"
      >
        <n-icon :size="19">
          <ChevronBackOutline />
        </n-icon>
      </button>

      <div class="birthday-grid">
        <button
          v-for="b in currentSlide"
          :key="b.id"
          type="button"
          class="birthday-card"
          :aria-label="`${displayName(b.full_name)}, ${formatDate(b.birth_date)}`"
          @click="openProfile(b.id)"
        >
          <UserAvatar
            :user="b"
            :size="38"
            class="birthday-card__avatar"
          />
          <div class="birthday-card__body">
            <span class="birthday-card__name">{{ displayName(b.full_name) }}</span>
            <span class="birthday-card__date">{{ formatDate(b.birth_date) }}</span>
          </div>
        </button>
      </div>

      <button
        type="button"
        class="nav-arrow"
        :disabled="currentPage >= slides.length - 1"
        :aria-label="t('common.next')"
        @click="next"
      >
        <n-icon :size="19">
          <ChevronForwardOutline />
        </n-icon>
      </button>
    </div>

    <!-- Точки-индикаторы страниц — только если страниц больше одной. -->
    <div
      v-if="slides.length > 1"
      class="dots"
    >
      <button
        v-for="(_, idx) in slides"
        :key="`dot-${idx}`"
        type="button"
        class="dot"
        :class="{ 'dot--active': idx === currentPage }"
        :aria-label="`${idx + 1}`"
        @click="currentPage = idx"
      />
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NIcon } from 'naive-ui'
import { ChevronBackOutline, ChevronForwardOutline } from '@vicons/ionicons5'
import { useRouter } from 'vue-router'
import { useBirthdaysQuery } from '../../queries/users'
import type { Birthday } from '../../api/users'
import UserAvatar from '../UserAvatar.vue'

const { t, locale } = useI18n()
const router = useRouter()

const { data } = useBirthdaysQuery()
const birthdays = computed(() => data.value?.items ?? [])

// Чанки по 6 (3 в ряд × 2 ряда) — каждый чанк = одна страница.
const PER_SLIDE = 6
const slides = computed<Birthday[][]>(() => {
  const items = birthdays.value
  const out: Birthday[][] = []
  for (let i = 0; i < items.length; i += PER_SLIDE) {
    out.push(items.slice(i, i + PER_SLIDE))
  }
  return out
})

const currentPage = ref(0)
const currentSlide = computed(() => slides.value[currentPage.value] ?? [])

// Сброс страницы, если данные обновились и текущая страница больше не валидна
// (например, именинников стало меньше после refetch).
watch(slides, (s) => {
  if (currentPage.value > s.length - 1) currentPage.value = Math.max(0, s.length - 1)
})

function prev() {
  if (currentPage.value > 0) currentPage.value -= 1
}
function next() {
  if (currentPage.value < slides.value.length - 1) currentPage.value += 1
}

// «День + месяц» в текущей локали (ru: «5 марта», en: «March 5»).
function formatDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00`)
  return new Intl.DateTimeFormat(locale.value, { day: 'numeric', month: 'long' }).format(d)
}

// Фамилия + имя без отчества: первые 2 слова.
function displayName(fullName: string): string {
  return fullName.trim().split(/\s+/).slice(0, 2).join(' ')
}

// Фоллбэк аватара (инициалы) и кольцо статуса — внутри UserAvatar.

function openProfile(id: string): void {
  router.push(`/users/${id}`)
}
</script>

<style scoped>
.widget {
  background: var(--color-mage-card, var(--color-surface));
  border: 1px solid var(--color-mage-border, var(--color-border));
  border-radius: var(--radius-card, var(--radius-lg));
  /* Сжато вдвое, затем +20%: 10×12×8 → 12×14×10 */
  padding: 12px 14px 10px;
  box-shadow: var(--shadow-soft, var(--shadow-sm));
}
.widget__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 7px;
}
.widget__title {
  margin: 0;
  font-size: 13px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--color-text-muted);
}

/* Сцена: [стрелка] [сетка] [стрелка] */
.birthdays-stage {
  display: flex;
  align-items: center;
  gap: 5px;
}

/* Сетка 3 колонки × 2 ряда. */
.birthday-grid {
  flex: 1 1 auto;
  min-width: 0;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 7px;
}

/* Кнопки-стрелки. */
.nav-arrow {
  flex: 0 0 auto;
  width: 29px;
  height: 29px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--color-border);
  border-radius: 50%;
  background: var(--color-surface, #fff);
  color: var(--color-text-muted);
  cursor: pointer;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}
.nav-arrow:hover:not(:disabled) {
  background: var(--color-bg-muted, #f5f5f5);
  color: var(--color-text);
  border-color: var(--color-text-muted);
}
.nav-arrow:disabled {
  opacity: 0.35;
  cursor: default;
}

/* Карточка именинника. */
.birthday-card {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 6px 8px;
  background: var(--color-bg, #fff);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  min-width: 0;
  cursor: pointer;
  text-align: left;
  font: inherit;
  color: inherit;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.birthday-card:hover {
  border-color: var(--color-brand-sky, #38bdf8);
  box-shadow: var(--shadow-sm);
}

.birthday-card__avatar {
  flex-shrink: 0;
  font-size: 13px;
  font-weight: 700;
  background: var(--color-brand-navy, #1f3a5f);
  color: #fff;
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

/* Точки-индикаторы. */
.dots {
  display: flex;
  justify-content: center;
  gap: 4px;
  margin-top: 7px;
}
.dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  border: none;
  padding: 0;
  background: var(--color-border, #ccc);
  cursor: pointer;
  transition: background 0.15s;
}
.dot--active {
  background: var(--color-text-muted, #888);
}

@media (max-width: 720px) {
  .birthday-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
