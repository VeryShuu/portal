<template>
  <section
    class="hero"
    :aria-label="t('home.heroAria')"
  >
    <div class="hero__bg">
      <svg
        class="hero__waves"
        viewBox="0 0 1440 320"
        preserveAspectRatio="none"
        aria-hidden="true"
      >
        <path
          fill="rgba(255,255,255,0.04)"
          d="M0,224L48,213.3C96,203,192,181,288,170.7C384,160,480,160,576,176C672,192,768,224,864,224C960,224,1056,192,1152,170.7C1248,149,1344,139,1392,133.3L1440,128L1440,320L0,320Z"
        />
        <path
          fill="rgba(255,255,255,0.06)"
          d="M0,256L60,250.7C120,245,240,235,360,229.3C480,224,600,224,720,229.3C840,235,960,245,1080,234.7C1200,224,1320,192,1380,176L1440,160L1440,320L0,320Z"
        />
      </svg>
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
          {{ branding.settings.welcome_subtitle || t('home.heroSub') }}
        </p>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '../stores/auth'
import { useBrandingStore } from '../stores/branding'

const { t, locale } = useI18n()
const auth = useAuthStore()
const branding = useBrandingStore()

const firstName = computed(() => {
  const fn = auth.user?.full_name?.trim()
  if (!fn) return t('home.greetingAnonymous')
  const parts = fn.split(/\s+/)
  const name = parts[0]
  return name
})

const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 6) return t('home.greetings.night')
  if (h < 12) return t('home.greetings.morning')
  if (h < 18) return t('home.greetings.afternoon')
  return t('home.greetings.evening')
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
  border-radius: var(--radius-xl);
  overflow: hidden;
  background: var(--gradient-hero);
  color: #fff;
  padding: 18px 28px;
  margin-bottom: 24px;
  box-shadow: var(--shadow-hero);
}
.hero__bg {
  position: absolute;
  inset: 0;
  pointer-events: none;
  overflow: hidden;
}
.hero__waves {
  position: absolute;
  bottom: 0;
  left: 0;
  width: 100%;
  height: 60%;
}
.hero__content {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 32px;
  flex-wrap: wrap;
}
.hero__text {
  flex: 1;
  min-width: 280px;
  max-width: 640px;
}
.hero__date {
  color: rgba(255, 255, 255, 0.7);
  margin-bottom: 8px;
}
.hero__greeting {
  font-size: 26px;
  line-height: 1.15;
  font-weight: 800;
  letter-spacing: -0.02em;
  color: #fff;
  margin: 0 0 4px 0;
}
.hero__sub {
  font-size: 14px;
  color: rgba(255, 255, 255, 0.78);
  margin: 0;
  max-width: 520px;
}

@media (max-width: 720px) {
  .hero { padding: 14px 18px; }
}
</style>
