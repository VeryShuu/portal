<template>
  <AppLayout>
    <template #header-title><span>{{ t('nav.links') }}</span></template>

    <div class="links-wrap">
      <header class="page-head">
        <div>
          <h1 class="page-head__title">{{ t('nav.links') }}</h1>
          <p class="page-head__sub">{{ t('links.pageSub') }}</p>
        </div>
      </header>

      <n-spin v-if="store.loadingLinks" style="margin:60px auto;display:block" />
      <template v-else>
        <EmptyState
          v-if="!Object.keys(store.groupedLinks).length"
          variant="default"
          :title="t('links.empty')"
          :description="t('links.emptyHint')"
        />

        <template v-for="(group, category) in store.groupedLinks" :key="category">
          <section class="category-section">
            <h3 class="category-title">{{ category }}</h3>
            <div class="links-grid">
              <button
                v-for="link in group"
                :key="link.id"
                type="button"
                class="link-card"
                @click="store.openLink(link)"
              >
                <div class="link-icon" :style="{ background: colorFor(link.url) }">
                  <img
                    v-if="link.icon_url"
                    :src="link.icon_url"
                    :alt="link.title"
                    @error="onIconError($event)"
                  />
                  <img
                    v-else-if="faviconFor(link.url)"
                    :src="faviconFor(link.url)!"
                    :alt="link.title"
                    @error="onIconError($event)"
                  />
                  <n-icon v-else size="22"><LinkOutline /></n-icon>
                </div>
                <div class="link-info">
                  <div class="link-title">
                    {{ link.title }}
                    <span v-if="link.supports_sso" class="sso-badge" :title="t('links.sso')">
                      <n-icon size="12"><ShieldCheckmarkOutline /></n-icon>
                      SSO
                    </span>
                  </div>
                  <div v-if="link.description" class="link-desc">{{ link.description }}</div>
                  <div class="link-url">{{ shortUrl(link.url) }}</div>
                </div>
                <n-icon class="link-arrow" size="16"><OpenOutline /></n-icon>
              </button>
            </div>
          </section>
        </template>
      </template>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { NSpin, NIcon } from 'naive-ui'
import { LinkOutline, ShieldCheckmarkOutline, OpenOutline } from '@vicons/ionicons5'
import AppLayout from '../components/AppLayout.vue'
import EmptyState from '../components/EmptyState.vue'
import { useLinksStore } from '../stores/links'

const { t } = useI18n()
const store = useLinksStore()

onMounted(() => store.loadLinks())

function faviconFor(url: string): string | null {
  try {
    const u = new URL(url)
    return `${u.origin}/favicon.ico`
  } catch {
    return null
  }
}

function shortUrl(url: string): string {
  try {
    const u = new URL(url)
    return u.hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}

const palette = [
  '#e0eafc', '#ffe4e1', '#ede4ff', '#dcfce7', '#fef3c7', '#e0f2fe', '#fce7f3',
]
function colorFor(url: string): string {
  let hash = 0
  for (let i = 0; i < url.length; i++) hash = (hash * 31 + url.charCodeAt(i)) >>> 0
  return palette[hash % palette.length]
}

function onIconError(e: Event) {
  const img = e.target as HTMLImageElement
  img.style.display = 'none'
}
</script>

<style scoped>
.links-wrap {
  max-width: 1200px;
  margin: 0 auto;
}
.page-head {
  margin-bottom: 24px;
}
.page-head__title {
  margin: 0;
  font-size: 26px;
  font-weight: 800;
  letter-spacing: -0.02em;
  color: var(--color-text);
}
.page-head__sub {
  margin: 4px 0 0;
  color: var(--color-text-muted);
  font-size: 14px;
}

.category-section {
  margin-bottom: 32px;
}
.category-title {
  font-size: 11px;
  font-weight: 700;
  margin: 0 0 14px;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.1em;
}

.links-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px;
}

.link-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 16px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  cursor: pointer;
  position: relative;
  text-align: left;
  font-family: inherit;
  width: 100%;
  transition: transform var(--t-base), box-shadow var(--t-base), border-color var(--t-base);
}
.link-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
  border-color: var(--color-brand-sky);
}
.link-card:hover .link-arrow {
  color: var(--color-brand-red);
  transform: translate(2px, -2px);
}

.link-icon {
  flex-shrink: 0;
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-md);
  overflow: hidden;
  color: var(--color-brand-navy);
}
.link-icon img {
  width: 26px;
  height: 26px;
  object-fit: contain;
}
.link-info {
  flex: 1;
  min-width: 0;
}
.link-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--color-text);
  display: flex;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.link-desc {
  font-size: 12px;
  color: var(--color-text-muted);
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.link-url {
  font-size: 11px;
  color: var(--color-text-subtle);
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.link-arrow {
  flex-shrink: 0;
  color: var(--color-text-subtle);
  transition: transform var(--t-base), color var(--t-base);
}

.sso-badge {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 1px 6px;
  border-radius: var(--radius-pill);
  background: rgba(74, 144, 196, 0.12);
  color: var(--color-brand-sky);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
</style>
