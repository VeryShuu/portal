<template>
  <div class="home u-page-wrap">
    <PortalBanner />

    <HeroBlock />

    <HomeFeaturedNewsSection
      :loading-news="loadingNews"
      :pinned="pinned"
      :categories-map="categoriesMap"
      @news-click="goToNews"
    />

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
        <HomeNewsGrid
          :loading-news="loadingNews"
          :regular="regular"
          :categories-map="categoriesMap"
          @news-click="goToNews"
        />

        <BirthdaysWidget />
      </div>

      <!-- Side column -->
      <aside class="home__side">
        <QuickServicesWidget />

        <WorldClockWidget />

        <MeetingsWidget />

        <PhotosWidget />

        <QuickLinksWidget />
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { NButton, NIcon } from 'naive-ui'
import { ChevronForwardOutline } from '@vicons/ionicons5'
import HeroBlock from '../components/HeroBlock.vue'
import BirthdaysWidget from '../components/widgets/BirthdaysWidget.vue'
import PhotosWidget from '../components/widgets/PhotosWidget.vue'
import WorldClockWidget from '../components/widgets/WorldClockWidget.vue'
import MeetingsWidget from '../components/widgets/MeetingsWidget.vue'
import QuickLinksWidget from '../components/widgets/QuickLinksWidget.vue'
import PortalBanner from '../components/widgets/PortalBanner.vue'
import HomeFeaturedNewsSection from '../components/widgets/HomeFeaturedNewsSection.vue'
import HomeNewsGrid from '../components/widgets/HomeNewsGrid.vue'
import QuickServicesWidget from '../components/widgets/QuickServicesWidget.vue'
import { useAuthStore } from '../stores/auth'
import { useHomeNews } from '../composables/useHomeNews'

const router = useRouter()
const auth = useAuthStore()
const { t } = useI18n()

const { loadingNews, pinned, regular, categoriesMap, goToNews } = useHomeNews()
</script>

<style scoped>
.home__grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: var(--space-outer, 24px); /* единая сетка отступов редизайна */
  align-items: flex-start;
}
.home__main { min-width: 0; }
.home__main > * + * { margin-top: var(--space-card-gap, 20px); }
.home__side {
  display: flex;
  flex-direction: column;
  gap: var(--space-card-gap, 20px);
  position: sticky;
  top: 16px;
}

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

/* === Responsive === */
/* Большие десктопы (FullHD 1600+): чуть шире контент, правая колонка стабильна 320px. */
@media (min-width: 1600px) {
  .home__grid { grid-template-columns: minmax(0, 1fr) 340px; }
}
/* Средние десктопы (1366–1440): правая колонка остаётся фиксированной до 1024px. */
@media (max-width: 1366px) {
  .home__grid { gap: 20px; }
}
@media (max-width: 1024px) {
  .home__grid { grid-template-columns: 1fr; }
  .home__side { position: static; }
}
</style>
