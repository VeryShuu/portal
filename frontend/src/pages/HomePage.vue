<template>
  <div class="home">
    <!-- Portal banner -->
    <div
      v-if="branding.isBannerActive && dismissedBannerKey !== bannerKey"
      class="portal-banner"
      :class="`portal-banner--${branding.settings.banner_type}`"
      role="alert"
    >
      <span class="portal-banner__text">{{ branding.settings.banner_text }}</span>
      <button
        class="portal-banner__close"
        :aria-label="t('common.close')"
        @click="dismissBanner"
      >
        ✕
      </button>
    </div>

    <HeroBlock />

    <!-- Featured (pinned) news — full width above the grid -->
    <section
      v-if="pinned.length || loadingNews"
      class="section section--featured"
    >
      <div class="section__header">
        <h2 class="section__title">
          {{ t('home.sections.featured') }}
        </h2>
      </div>

      <div
        v-if="loadingNews"
        class="featured-skeleton"
      >
        <SkeletonCard variant="news" />
      </div>
      <template v-else>
        <NewsCard
          v-for="item in pinned"
          :key="item.id"
          :news="item"
          featured
          :categories-map="categoriesMap"
          class="featured-card"
          @click="goToNews"
        />
      </template>
    </section>

    <!-- Latest news header — full width above the grid -->
    <div class="section__header news-header">
      <h2 class="section__title">
        {{ t('home.sections.latest') }}
      </h2>
      <div class="section__actions">
        <n-button
          v-if="auth.isEditor"
          type="primary"
          size="small"
          @click="router.push('/news/create')"
        >
          + {{ t('news.create.title') }}
        </n-button>
        <n-button
          text
          type="primary"
          size="small"
          @click="router.push('/news')"
        >
          {{ t('home.viewAll') }}
          <template #icon>
            <n-icon><ChevronForwardOutline /></n-icon>
          </template>
        </n-button>
      </div>
    </div>

    <div class="home__grid">
      <!-- Main column -->
      <div class="home__main">
        <div
          v-if="loadingNews"
          class="news-grid"
        >
          <SkeletonCard
            v-for="i in 4"
            :key="`sk-${i}`"
            variant="news"
          />
        </div>
        <div
          v-else-if="regular.length"
          class="news-grid"
        >
          <NewsCard
            v-for="item in regular"
            :key="item.id"
            :news="item"
            :categories-map="categoriesMap"
            @click="goToNews"
          />
        </div>
        <EmptyState
          v-else
          variant="news"
          :title="t('news.noNews')"
        />
      </div>

      <!-- Side column -->
      <aside class="home__side">
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

        <WorldClockWidget />

        <MeetingsWidget />

        <PhotosWidget />

        <section
          v-if="recentArticles.length"
          class="widget"
        >
          <div class="widget__header">
            <h3 class="widget__title">
              {{ t('home.sections.recentArticles') }}
            </h3>
            <n-button
              text
              size="tiny"
              @click="router.push('/kb')"
            >
              {{ t('common.all') }}
            </n-button>
          </div>
          <ul class="recent-articles-list">
            <li
              v-for="a in recentArticles"
              :key="a.id"
              class="recent-article-row"
            >
              <n-button
                text
                class="recent-article-row__link"
                @click="router.push(`/kb/articles/${a.id}`)"
              >
                {{ a.title }}
              </n-button>
            </li>
          </ul>
        </section>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  NButton, NIcon,
} from 'naive-ui'
import { ChevronForwardOutline } from '@vicons/ionicons5'
import HeroBlock from '../components/HeroBlock.vue'
import NewsCard from '../components/NewsCard.vue'
import EmptyState from '../components/EmptyState.vue'
import SkeletonCard from '../components/SkeletonCard.vue'
import PhotosWidget from '../components/widgets/PhotosWidget.vue'
import WorldClockWidget from '../components/widgets/WorldClockWidget.vue'
import MeetingsWidget from '../components/widgets/MeetingsWidget.vue'
import { useAuthStore } from '../stores/auth'
import { useLinksStore } from '../stores/links'
import { useBrandingStore } from '../stores/branding'
import { useKbArticlesQuery } from '../queries/kb'
import { useHomeNews } from '../composables/useHomeNews'

const router = useRouter()
const auth = useAuthStore()
const linksStore = useLinksStore()
const branding = useBrandingStore()
const { t } = useI18n()

const BANNER_DISMISS_KEY = 'home_banner_dismissed'
const bannerKey = computed(
  () => `${branding.settings.banner_text}|${branding.settings.banner_expires_at ?? ''}`,
)
const dismissedBannerKey = ref<string | null>(
  typeof sessionStorage !== 'undefined' ? sessionStorage.getItem(BANNER_DISMISS_KEY) : null,
)
function dismissBanner() {
  dismissedBannerKey.value = bannerKey.value
  if (typeof sessionStorage !== 'undefined') {
    sessionStorage.setItem(BANNER_DISMISS_KEY, bannerKey.value)
  }
}

const { data: kbArticlesData } = useKbArticlesQuery({ status: 'published', limit: 5 })
const recentArticles = computed(() => kbArticlesData.value?.items ?? [])

const topLinks = computed(() => linksStore.links.slice(0, 6))

const { loadingNews, pinned, regular, categoriesMap, goToNews } = useHomeNews()

</script>

<style scoped>
.home {
  max-width: 1280px;
  margin: 0 auto;
}
.home__grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 24px;
  align-items: flex-start;
}
.home__main { min-width: 0; }
.home__side {
  display: flex;
  flex-direction: column;
  gap: 20px;
  position: sticky;
  top: 16px;
}

/* === Section === */
.section { margin-bottom: 32px; }
.section--featured { margin-bottom: 0; }
.news-header { margin-bottom: 14px; }
.section__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
  gap: 12px;
  flex-wrap: wrap;
}
.section__title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--color-text);
}
.section__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* === News grid === */
.news-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}
.featured-card,
.featured-skeleton { margin-bottom: 4px; }

/* === Widgets === */
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

/* Quick services grid */
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

/* === Banner === */
.portal-banner {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 18px;
  border-radius: var(--radius-md);
  margin-bottom: 16px;
  font-size: 14px;
  font-weight: 500;
}
.portal-banner--info    { background: #e0eafc; color: #1a4b8c; }
.portal-banner--warning { background: #fef3c7; color: #92400e; }
.portal-banner--error   { background: #fde8e9; color: #9b1c1c; }
.portal-banner--success { background: #dcfce7; color: #14532d; }
.portal-banner__text { flex: 1; }
.portal-banner__close {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 16px;
  opacity: 0.6;
  padding: 0 4px;
  color: inherit;
  line-height: 1;
}
.portal-banner__close:hover { opacity: 1; }

/* === Recent articles widget === */
.recent-articles-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.recent-article-row { min-width: 0; }
.recent-article-row__link {
  width: 100%;
  text-align: left;
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: block;
  max-width: 100%;
}

/* === Responsive === */
@media (max-width: 1100px) {
  .home__grid { grid-template-columns: 1fr; }
  .home__side { position: static; }
}
@media (max-width: 720px) {
  .news-grid { grid-template-columns: 1fr; }
}
</style>
