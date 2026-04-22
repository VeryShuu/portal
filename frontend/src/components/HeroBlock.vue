<template>
  <section class="hero" role="region" :aria-label="t('home.heroAria')">
    <div class="hero__bg">
      <svg class="hero__waves" viewBox="0 0 1440 320" preserveAspectRatio="none" aria-hidden="true">
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
        <div class="hero__date u-uppercase">{{ formattedDate }}</div>
        <h1 class="hero__greeting">
          {{ greeting }}<span v-if="firstName">, {{ firstName }}</span>
        </h1>
        <p class="hero__sub">{{ t('home.heroSub') }}</p>

        <button class="hero__search" type="button" :aria-label="t('nav.openSearch')" @click="openSearch">
          <n-icon size="18"><SearchOutline /></n-icon>
          <span class="hero__search-text">{{ t('home.searchPlaceholder') }}</span>
          <kbd class="hero__search-kbd">Ctrl K</kbd>
        </button>
      </div>

      <div class="hero__stats">
        <article class="stat" v-for="s in stats" :key="s.key">
          <div class="stat__num">{{ s.value }}</div>
          <div class="stat__label">{{ s.label }}</div>
        </article>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NIcon } from 'naive-ui'
import { SearchOutline } from '@vicons/ionicons5'
import { useAuthStore } from '../stores/auth'

interface Stat {
  key: string
  value: number | string
  label: string
}

const props = defineProps<{
  stats?: Stat[]
}>()

const { t, locale } = useI18n()
const auth = useAuthStore()

const firstName = computed(() => {
  const fn = auth.user?.full_name?.trim()
  if (!fn) return ''
  // For Russian "Иванов Иван Иванович" — take 2nd word, else 1st
  const parts = fn.split(/\s+/)
  return parts.length >= 2 ? parts[1] : parts[0]
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

const stats = computed<Stat[]>(() => props.stats ?? [])

function openSearch() {
  window.dispatchEvent(new CustomEvent('open-global-search'))
}
</script>

<style scoped>
.hero {
  position: relative;
  border-radius: var(--radius-xl);
  overflow: hidden;
  background: var(--gradient-hero);
  color: #fff;
  padding: 28px 32px;
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
  font-size: 32px;
  line-height: 1.15;
  font-weight: 800;
  letter-spacing: -0.02em;
  color: #fff;
  margin: 0 0 6px 0;
}
.hero__sub {
  font-size: 14px;
  color: rgba(255, 255, 255, 0.78);
  margin: 0 0 20px 0;
  max-width: 520px;
}

.hero__search {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  max-width: 520px;
  height: 46px;
  padding: 0 16px;
  background: rgba(255, 255, 255, 0.95);
  color: var(--color-text);
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-family: inherit;
  font-size: 14px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.18);
  transition: transform var(--t-fast), box-shadow var(--t-fast);
}
.hero__search:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.22);
}
.hero__search :deep(.n-icon) { color: var(--color-text-muted); }
.hero__search-text {
  flex: 1;
  text-align: left;
  color: var(--color-text-muted);
}
.hero__search-kbd {
  font-family: ui-monospace, monospace;
  font-size: 11px;
  padding: 3px 7px;
  border-radius: 4px;
  background: var(--color-bg-muted);
  color: var(--color-text-muted);
  border: 1px solid var(--color-border);
}

.hero__stats {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.stat {
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.18);
  backdrop-filter: blur(4px);
  border-radius: var(--radius-lg);
  padding: 18px 24px;
  min-width: 120px;
  text-align: left;
}
.stat__num {
  font-size: 32px;
  font-weight: 800;
  letter-spacing: -0.02em;
  line-height: 1;
  color: #fff;
  margin-bottom: 6px;
}
.stat__label {
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: rgba(255, 255, 255, 0.75);
  font-weight: 600;
}

@media (max-width: 720px) {
  .hero { padding: 22px 20px; }
  .hero__greeting { font-size: 26px; }
  .hero__stats { width: 100%; }
  .stat { flex: 1; min-width: 100px; padding: 14px; }
  .stat__num { font-size: 24px; }
}
</style>
