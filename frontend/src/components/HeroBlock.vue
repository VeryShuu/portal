<template>
  <section
    class="hero"
    :class="[`hero--${heroSlot}`, { 'hero--has-photo': heroPhotoUrl }]"
    :aria-label="t('home.heroAria')"
  >
    <!-- Фон: фото выбранного слота (если загружено) или CSS-градиент по времени -->
    <div class="hero__bg">
      <img
        v-if="heroPhotoUrl"
        :src="heroPhotoUrl"
        alt=""
        class="hero__photo"
        loading="lazy"
        decoding="async"
        aria-hidden="true"
      >
      <!-- Затемняющий градиент слева→направо для читаемости текста поверх фото
           (концепт: rgba(20,50,100,.75) → rgba(20,50,100,.15)) -->
      <div
        v-if="heroPhotoUrl"
        class="hero__scrim"
      />
    </div>

    <div class="hero__content">
      <!-- Левая часть: дата + приветствие + подпись + кнопка -->
      <div class="hero__text">
        <div class="hero__date u-uppercase">
          {{ formattedDate }}
        </div>
        <h1 class="hero__greeting">
          {{ greeting }}<span v-if="firstName">, {{ firstName }}</span>
        </h1>
        <p class="hero__sub">
          {{ heroSubtitle }}
        </p>
        <n-button
          class="hero__cta"
          type="primary"
          size="large"
          @click="router.push('/news')"
        >
          {{ t('home.viewNews') }}
        </n-button>
      </div>

      <!-- Правая часть: белая карточка «Сегодня» поверх баннера (концепт) -->
      <aside
        v-if="showStatsCard"
        class="hero__stats"
        :aria-label="t('home.statsToday')"
      >
        <div class="hero__stats-title">
          {{ t('home.statsToday') }}
        </div>
        <ul class="hero__stats-list">
          <li class="hero__stats-row">
            <span class="hero__stats-icon">
              <n-icon :size="18"><NewspaperOutline /></n-icon>
            </span>
            <span class="hero__stats-label">{{ t('home.stats.newsCount') }}</span>
            <span
              class="hero__stats-value"
              :class="{ 'hero__stats-value--loading': stats.loading }"
            >{{ stats.newsCount }}</span>
          </li>
          <li
            v-if="meetingsEnabled"
            class="hero__stats-row"
          >
            <span class="hero__stats-icon">
              <n-icon :size="18"><CalendarOutline /></n-icon>
            </span>
            <span class="hero__stats-label">{{ t('home.stats.meetingsToday') }}</span>
            <span
              class="hero__stats-value"
              :class="{ 'hero__stats-value--loading': stats.loading }"
            >{{ stats.meetingsToday }}</span>
          </li>
          <li
            v-if="stats.showTasks"
            class="hero__stats-row"
          >
            <span class="hero__stats-icon">
              <n-icon :size="18"><CheckboxOutline /></n-icon>
            </span>
            <span class="hero__stats-label">{{ t('home.stats.myTasks') }}</span>
            <span
              class="hero__stats-value"
              :class="{ 'hero__stats-value--loading': stats.loading }"
            >{{ stats.myTasks }}</span>
          </li>
        </ul>
      </aside>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NIcon } from 'naive-ui'
import { NewspaperOutline, CalendarOutline, CheckboxOutline } from '@vicons/ionicons5'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useBrandingStore } from '../stores/branding'
import { useModulesStore } from '../stores/modules'
import { useHeroStats } from '../composables/useHeroStats'

type HeroSlot = 'morning' | 'day' | 'evening'

const { t, locale } = useI18n()
const router = useRouter()
const auth = useAuthStore()
const branding = useBrandingStore()
const modules = useModulesStore()
const { stats } = useHeroStats()

// Карточка «Сегодня» показывается всегда (как в концепте). Строка «Встречи» —
// только если модуль meetings включён; «Мои задачи» — если helpdesk включён
// (useHeroStats.showTasks). Таким образом карточка адаптируется к набору
// активных модулей, не показывая нерелевантные строки.
const meetingsEnabled = computed(() => modules.isEnabled('meetings'))
const showStatsCard = computed(() => true)

// Текущий час — реактивный, обновляется ежечасно, чтобы Hero сам переключал
// слот/приветствие при смене времени без перезагрузки страницы.
const nowHour = ref(new Date().getHours())
let hourTimer: ReturnType<typeof setInterval> | null = null
onMounted(() => {
  hourTimer = setInterval(() => {
    nowHour.value = new Date().getHours()
  }, 60 * 1000)
})
onBeforeUnmount(() => {
  if (hourTimer) clearInterval(hourTimer)
})

const firstName = computed(() => {
  const fn = auth.user?.full_name?.trim()
  if (!fn) return t('home.greetingAnonymous')
  const parts = fn.split(/\s+/)
  const name = parts.length > 1 ? parts[1] : parts[0]
  return name
})

const greeting = computed(() => {
  const h = nowHour.value
  if (h < 6) return t('home.greetings.night')
  if (h < 12) return t('home.greetings.morning')
  if (h < 18) return t('home.greetings.afternoon')
  return t('home.greetings.evening')
})

// Активный слот фона по часу + настраиваемым границам из BrandingSettings.
const heroSlot = computed<HeroSlot>(() => {
  const h = nowHour.value
  const day = branding.settings.hero_day_hour ?? 12
  const evening = branding.settings.hero_evening_hour ?? 18
  if (h >= evening || h < (branding.settings.hero_morning_hour ?? 6)) return 'evening'
  if (h >= day) return 'day'
  return 'morning'
})

const heroSubtitle = computed(() => {
  // Глобальный welcome_subtitle из branding имеет приоритет (override admin'а),
  // иначе — per-time подпись из ТЗ редизайна.
  const override = branding.settings.welcome_subtitle?.trim()
  if (override) return override
  return t(`home.heroSubs.${heroSlot.value}`)
})

// URL фото активного слота, если админ его загрузил (has_hero_bg_*).
const heroPhotoUrl = computed(() => {
  const slot = heroSlot.value
  const hasFlag = {
    morning: branding.settings.has_hero_bg_morning,
    day: branding.settings.has_hero_bg_day,
    evening: branding.settings.has_hero_bg_evening,
  }[slot]
  return hasFlag ? branding.assetUrl(`hero-bg-${slot}` as never) : null
})

const formattedDate = computed(() => {
  const lang = locale.value === 'ru' ? 'ru-RU' : 'en-US'
  return new Date().toLocaleDateString(lang, {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  })
})
</script>

<style scoped>
.hero {
  position: relative;
  border-radius: var(--radius-hero); /* 20px */
  overflow: hidden;
  color: #fff;
  /* Высота ~250px (концепт): контент центрируется вертикально */
  min-height: 250px;
  display: flex;
  align-items: center;
  padding: 36px 40px;
  margin-bottom: var(--space-outer); /* 24px */
  box-shadow: var(--shadow-soft);
}

/* Градиент-fallback по времени суток (когда нет загруженного фото) */
.hero--morning { background: var(--gradient-hero-morning); }
.hero--day { background: var(--gradient-hero-day); }
.hero--evening { background: var(--gradient-hero-evening); }

/* Когда есть фото — базовый фон убираем, фото рисуется поверх */
.hero--has-photo {
  background: var(--color-brand-navy); /* запасной цвет под фото */
}

.hero__bg {
  position: absolute;
  inset: 0;
  pointer-events: none;
  overflow: hidden;
}
.hero__photo {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
}
/* Затемнение слева→направо (концепт): текст слева всегда читается поверх фото */
.hero__scrim {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    90deg,
    rgba(20, 50, 100, 0.75) 0%,
    rgba(20, 50, 100, 0.45) 50%,
    rgba(20, 50, 100, 0.15) 100%
  );
}

.hero__content {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 32px;
  flex-wrap: wrap;
  width: 100%;
}
.hero__text {
  flex: 1;
  min-width: 300px;
  max-width: 620px;
}
.hero__date {
  color: rgba(255, 255, 255, 0.85);
  margin-bottom: 12px;
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0.04em;
}
.hero__greeting {
  /* Концепт: ~42px, Semibold/Bold */
  font-size: var(--fs-hero-title, 42px);
  line-height: 1.1;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: #fff;
  margin: 0 0 10px 0;
}
.hero__sub {
  font-size: var(--fs-body, 16px);
  line-height: 1.5;
  color: rgba(255, 255, 255, 0.88);
  margin: 0 0 20px 0;
  max-width: 520px;
}
.hero__cta {
  /* Navy кнопка с белым текстом (концепт). Использует mage-primary, а не
     глобальный brand-red, т.к. это декоративный CTA внутри Hero. */
  --n-color: var(--color-mage-primary);
  --n-color-hover: var(--color-mage-secondary);
  --n-color-pressed: var(--color-mage-primary);
  --n-text-color: #fff;
  border-radius: var(--radius-button);
  font-weight: 600;
}

/* Правая белая карточка «Сегодня» (концепт: ~270×180, radius 18) */
.hero__stats {
  flex: 0 0 auto;
  width: 280px;
  background: var(--color-mage-card, #fff);
  border-radius: 18px;
  padding: 18px 20px;
  box-shadow: 0 10px 30px rgba(11, 42, 74, 0.18);
  color: var(--color-mage-text, #1f2937);
}
.hero__stats-title {
  font-size: 13px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--color-mage-text-secondary, #6b7280);
  margin-bottom: 12px;
}
.hero__stats-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.hero__stats-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.hero__stats-icon {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-mini, 12px);
  background: color-mix(in srgb, var(--color-mage-secondary, #2f6cb5) 12%, transparent);
  color: var(--color-mage-primary, #1f4e8c);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.hero__stats-label {
  flex: 1;
  font-size: 14px;
  color: var(--color-mage-text, #1f2937);
}
.hero__stats-value {
  font-size: 18px;
  font-weight: 700;
  color: var(--color-mage-primary, #1f4e8c);
  font-variant-numeric: tabular-nums;
}
.hero__stats-value--loading {
  opacity: 0.4;
}

/* Адаптивность */
@media (max-width: 1280px) {
  .hero { padding: 30px 28px; }
  .hero__greeting { font-size: 36px; }
  .hero__stats { width: 250px; }
}
@media (max-width: 1024px) {
  .hero__stats { width: 240px; padding: 14px 16px; }
}
@media (max-width: 720px) {
  .hero {
    padding: 24px 20px;
    min-height: 220px;
  }
  .hero__greeting { font-size: 28px; }
  .hero__sub { font-size: 14px; }
  .hero__content { flex-direction: column; align-items: flex-start; }
  .hero__stats { width: 100%; }
}

/* Dark mode: hero фото/градиенты уже тёмные, текст остаётся светлым.
   Карточка stats наследует dark surface. Scrim чуть усиливаем для тёмного фото. */
[data-theme='dark'] .hero__scrim {
  background: linear-gradient(
    90deg,
    rgba(7, 20, 38, 0.85) 0%,
    rgba(7, 20, 38, 0.5) 50%,
    rgba(7, 20, 38, 0.2) 100%
  );
}
</style>
