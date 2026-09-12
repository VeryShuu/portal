<template>
  <section class="widget">
    <div class="widget__header">
      <h3 class="widget__title">
        {{ t('home.sections.services') }}
      </h3>
      <n-button
        text
        size="tiny"
        @click="router.push('/links')"
      >
        {{ t('common.all') }}
      </n-button>
    </div>
    <div
      v-if="linksStore.loadingLinks"
      class="widget__body widget__body--loading"
    >
      <div
        v-for="i in 8"
        :key="`qsk-${i}`"
        class="quick-skeleton"
      />
    </div>
    <div
      v-else-if="topLinks.length"
      class="quick-grid"
    >
      <button
        v-for="link in topLinks"
        :key="link.id"
        class="quick-tile"
        type="button"
        :title="link.title"
        :aria-label="link.title"
        @click="linksStore.openLink(link)"
      >
        <div class="quick-tile__icon">
          <img
            v-if="link.icon_url"
            :src="link.icon_url"
            :alt="link.title"
            width="26"
            height="26"
            loading="lazy"
            decoding="async"
          >
          <span
            v-else
            class="quick-tile__letter"
          >{{ link.title.charAt(0).toUpperCase() }}</span>
        </div>
        <span class="quick-tile__name">{{ link.title }}</span>
      </button>
    </div>
    <EmptyState
      v-else
      compact
      variant="default"
      :title="t('links.empty')"
    />
  </section>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { NButton } from 'naive-ui'
import EmptyState from '../EmptyState.vue'
import { useHomeLinksPreview } from '../../pages/composables/useHomeLinksPreview'

const router = useRouter()
const { t } = useI18n()
const { linksStore, topLinks } = useHomeLinksPreview()
</script>

<style scoped>
.widget {
  background: var(--color-mage-card, var(--color-surface));
  border: 1px solid var(--color-mage-border, var(--color-border));
  border-radius: var(--radius-card, var(--radius-lg)); /* 16px — единый радиус редизайна */
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
.widget__body--loading {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* Плитки сервисов: 4 колонки × 2 ряда. Иконка резиновая (aspect-ratio, не
   фиксированная) — плитки сжимаются под ширину узкого aside, не вылезая за блок. */
.quick-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}
.quick-tile {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 8px 4px;
  min-width: 0; /* критично: grid-item должен сжиматься ниже контента */
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-family: inherit;
  transition: background var(--t-fast), border-color var(--t-fast), transform var(--t-fast);
}
.quick-tile:hover {
  /* Лёгкая navy-подсветка при наведении (ТЗ) */
  background: color-mix(in srgb, var(--color-mage-secondary, #2f6cb5) 10%, transparent);
  border-color: color-mix(in srgb, var(--color-mage-secondary, #2f6cb5) 30%, transparent);
  transform: translateY(-1px);
}
.quick-tile__icon {
  /* Резиновая иконка: занимает ширину плитки, квадрат через aspect-ratio.
    Раньше фиксированные 56px не давали плиткам сжиматься → вылезали за блок. */
  width: 100%;
  aspect-ratio: 1;
  border-radius: var(--radius-lg);
  background: var(--color-mage-card, #fff);
  border: 1px solid var(--color-mage-border, var(--color-border));
  box-shadow: var(--shadow-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  transition: box-shadow var(--t-fast), transform var(--t-fast);
}
[data-theme='dark'] .quick-tile__icon {
  background: rgba(255, 255, 255, 0.06);
}
.quick-tile:hover .quick-tile__icon {
  box-shadow: var(--shadow-md);
  transform: translateY(-1px);
}
.quick-tile__icon img { width: 100%; height: 100%; object-fit: cover; }
.quick-tile__letter {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  font-weight: 700;
  color: #fff;
  background: linear-gradient(135deg, var(--color-mage-secondary, var(--color-brand-sky)), var(--color-mage-primary, var(--color-brand-navy)));
}
.quick-tile__name {
  font-size: 11px;
  text-align: center;
  color: var(--color-mage-text, var(--color-text));
  line-height: 1.2;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-word;
}
.quick-skeleton {
  height: 90px;
  border-radius: var(--radius-md);
  background: var(--color-bg-muted);
  animation: pulse 1.4s ease-in-out infinite;
}
/* На узком aside (ноутбуки ≤1440) — 3 колонки вместо 4: плитки крупнее,
   не вылезают за границы блока при длинных названиях. */
@media (max-width: 1440px) {
  .quick-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}
</style>
