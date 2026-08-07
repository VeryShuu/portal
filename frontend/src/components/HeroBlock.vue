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
        <p class="hero__sub">
          {{ heroSubtitle }}
        </p>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '../stores/auth'
import { useBrandingStore } from '../stores/branding'

type HeroSlot = 'morning' | 'day' | 'evening'

const { t, locale } = useI18n()
const auth = useAuthStore()
const branding = useBrandingStore()

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
// Границы по умолчанию: утро 6-12, день 12-18, вечер 18-6 (настройше admin'ом).
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
  /* Высота 220-260px (ТЗ): контент центрируется вертикально */
  min-height: 240px;
  display: flex;
  align-items: center;
  padding: 32px 36px;
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
/* Затемнение слева→направо: текст слева всегда читается поверх фото */
.hero__scrim {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    90deg,
    rgba(11, 42, 74, 0.86) 0%,
    rgba(11, 42, 74, 0.55) 45%,
    rgba(11, 42, 74, 0.25) 100%
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
  min-width: 280px;
  max-width: 640px;
}
.hero__date {
  color: rgba(255, 255, 255, 0.82);
  margin-bottom: 10px;
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0.01em;
}
.hero__greeting {
  font-size: 30px;
  line-height: 1.15;
  font-weight: 800;
  letter-spacing: -0.02em;
  color: #fff;
  margin: 0 0 8px 0;
}
.hero__sub {
  font-size: 15px;
  line-height: 1.5;
  color: rgba(255, 255, 255, 0.86);
  margin: 0;
  max-width: 520px;
}

/* Адаптивность */
@media (max-width: 1280px) {
  .hero { padding: 28px 28px; }
  .hero__greeting { font-size: 27px; }
}
@media (max-width: 720px) {
  .hero {
    padding: 22px 20px;
    min-height: 200px;
  }
  .hero__greeting { font-size: 23px; }
  .hero__sub { font-size: 14px; }
}

/* Dark mode: hero фото/градиенты уже тёмные, текст остаётся светлым.
   Scrim чуть усиливаем для тёмного фото. */
[data-theme='dark'] .hero__scrim {
  background: linear-gradient(
    90deg,
    rgba(7, 20, 38, 0.9) 0%,
    rgba(7, 20, 38, 0.6) 45%,
    rgba(7, 20, 38, 0.3) 100%
  );
}
</style>
