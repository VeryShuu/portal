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
        v-for="i in 6"
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
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 16px 18px 12px;
  box-shadow: var(--shadow-sm);
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
.widget__body--loading {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.quick-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}
.quick-tile {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 10px 6px;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-family: inherit;
  transition: background var(--t-fast), border-color var(--t-fast), transform var(--t-fast);
}
.quick-tile:hover {
  background: var(--color-bg-muted);
  border-color: var(--color-border);
  transform: translateY(-1px);
}
.quick-tile__icon {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-md);
  background: var(--color-brand-ice);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}
[data-theme='dark'] .quick-tile__icon {
  background: rgba(255, 255, 255, 0.07);
}
.quick-tile__icon img { width: 26px; height: 26px; object-fit: contain; }
.quick-tile__letter {
  font-size: 18px;
  font-weight: 700;
  color: var(--color-brand-navy);
}
.quick-tile__name {
  font-size: 11px;
  text-align: center;
  color: var(--color-text);
  line-height: 1.2;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  max-width: 80px;
}
.quick-skeleton {
  height: 68px;
  border-radius: var(--radius-md);
  background: var(--color-bg-muted);
  animation: pulse 1.4s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}
</style>
