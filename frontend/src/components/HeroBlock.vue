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
        :style="heroPhotoStyle"
        loading="lazy"
        decoding="async"
        aria-hidden="true"
      >
      <!-- Затемняющий градиент слева→направо для читаемости текста поверх фото -->
      <div
        v-if="heroPhotoUrl"
        class="hero__scrim"
      />
    </div>

    <div class="hero__content">
      <div class="hero__text">
        <div class="hero__date u-uppercase">
          {{ formattedDate }}
        </div>
        <h1 class="hero__greeting">
          {{ greeting }}<span v-if="firstName">, {{ firstName }}</span>
        </h1>
        <p
          v-if="heroSubtitle"
          class="hero__sub"
        >
          {{ heroSubtitle }}
        </p>
      </div>
    </div>

    <!-- Стеклянная карточка с временем в городах — в правом верхнем углу Hero
         (абсолютное позиционирование, не центрируется с текстом). -->
    <HeroWorldClock class="hero__clock" />
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '../stores/auth'
import { useBrandingStore } from '../stores/branding'
import { focalImageStyle } from '../utils/coverFocal'
import HeroWorldClock from './widgets/HeroWorldClock.vue'

type HeroSlot = 'morning' | 'day' | 'evening'

const { t, locale } = useI18n()
const auth = useAuthStore()
const branding = useBrandingStore()

// Текущий час — реактивный, обновляется ежечасно.
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

const heroSlot = computed<HeroSlot>(() => {
  const h = nowHour.value
  const day = branding.settings.hero_day_hour ?? 12
  const evening = branding.settings.hero_evening_hour ?? 18
  if (h >= evening || h < (branding.settings.hero_morning_hour ?? 6)) return 'evening'
  if (h >= day) return 'day'
  return 'morning'
})

const heroSubtitle = computed(() => {
  // Режим подзаголовка (настраивается в админке BrandingTab):
  // - auto: стандартные per-time подписи из i18n (утро/день/вечер/ночь)
  // - custom: свои тексты по слотам (hero_subtitle_morning/day/evening/night);
  //   если для слота не задано — fallback на стандартный i18n
  // - hidden: подзаголовок не показывается
  const mode = branding.settings.hero_subtitle_mode ?? 'auto'
  if (mode === 'hidden') return ''
  const slot = heroSlot.value
  if (mode === 'custom') {
    const customTexts: Record<string, string | undefined> = {
      morning: branding.settings.hero_subtitle_morning,
      day: branding.settings.hero_subtitle_day,
      evening: branding.settings.hero_subtitle_evening,
      night: branding.settings.hero_subtitle_night,
    }
    const custom = customTexts[slot]?.trim()
    return custom || t(`home.heroSubs.${slot}`)
  }
  return t(`home.heroSubs.${slot}`)
})

const heroPhotoUrl = computed(() => {
  const slot = heroSlot.value
  const hasFlag = {
    morning: branding.settings.has_hero_bg_morning,
    day: branding.settings.has_hero_bg_day,
    evening: branding.settings.has_hero_bg_evening,
  }[slot]
  return hasFlag ? branding.assetUrl(`hero-bg-${slot}` as never) : null
})

// Focal-point позиционирование фото Hero (настраивается в админке). null-значения
// дают центрирование без zoom — обратно совместимо с ранее загруженными фото.
const heroPhotoStyle = computed(() => {
  const slot = heroSlot.value
  const focalMap = {
    morning: {
      x: branding.settings.hero_bg_morning_focal_x,
      y: branding.settings.hero_bg_morning_focal_y,
      zoom: branding.settings.hero_bg_morning_focal_zoom,
    },
    day: {
      x: branding.settings.hero_bg_day_focal_x,
      y: branding.settings.hero_bg_day_focal_y,
      zoom: branding.settings.hero_bg_day_focal_zoom,
    },
    evening: {
      x: branding.settings.hero_bg_evening_focal_x,
      y: branding.settings.hero_bg_evening_focal_y,
      zoom: branding.settings.hero_bg_evening_focal_zoom,
    },
  }[slot]
  return focalImageStyle(focalMap.x, focalMap.y, focalMap.zoom)
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
  display: flex;
  align-items: center;
  min-height: 220px;
  padding: 28px 36px;
  margin-bottom: 16px;
  box-shadow: var(--shadow-soft);
}

/* Градиент-fallback по времени суток (когда нет загруженного фото) */
.hero--morning { background: var(--gradient-hero-morning); }
.hero--day { background: var(--gradient-hero-day); }
.hero--evening { background: var(--gradient-hero-evening); }

.hero--has-photo {
  background: var(--color-brand-navy);
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
  gap: 24px;
  flex-wrap: wrap;
  width: 100%;
}
.hero__text {
  flex: 1;
  min-width: 280px;
  max-width: 620px;
}
.hero__date {
  color: rgba(255, 255, 255, 0.85);
  margin-bottom: 6px;
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0.04em;
}
.hero__greeting {
  /* clamp: плавная адаптивность — растёт/падает с шириной экрана (п.8 UX-аудита). */
  font-size: clamp(24px, 2.4vw, 34px);
  line-height: 1.15;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: #fff;
  margin: 0 0 8px 0;
}
.hero__sub {
  font-size: 15px;
  line-height: 1.45;
  color: rgba(255, 255, 255, 0.88);
  margin: 0;
  max-width: 520px;
}

/* Карточка часов — правый верхний угол Hero (absolute, не центрируется с текстом). */
.hero__clock {
  position: absolute;
  top: 20px;
  right: 20px;
  z-index: 2;
}

@media (max-width: 1280px) {
  .hero { padding: 24px 28px; min-height: 190px; }
}
@media (max-width: 720px) {
  .hero { padding: 20px 18px; min-height: 160px; }
  .hero__greeting { font-size: 24px; }
  .hero__sub { font-size: 14px; }
}

[data-theme='dark'] .hero__scrim {
  background: linear-gradient(
    90deg,
    rgba(7, 20, 38, 0.85) 0%,
    rgba(7, 20, 38, 0.5) 50%,
    rgba(7, 20, 38, 0.2) 100%
  );
}
</style>
