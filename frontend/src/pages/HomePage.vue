<template>
  <div class="home u-page-wrap">
    <PortalBanner />

    <!-- HERO — отдельный блок над контентом, на всю ширину основной колонки.
         Не входит ни в какой grid. -->
    <HeroBlock />

    <!-- КОНТЕНТ: flex (НЕ grid). main flex:1 + aside фиксированной ширины. -->
    <div class="home__content">
      <!-- MAIN: новости -->
      <main class="home__main">
        <HomeFeaturedNewsSection
          :loading-news="loadingNews"
          :pinned="pinned"
          :categories-map="categoriesMap"
          @news-click="goToNews"
        />

        <!-- Latest news header — над сеткой новостей -->
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

        <HomeNewsGrid
          :loading-news="loadingNews"
          :regular="regular"
          :categories-map="categoriesMap"
          @news-click="goToNews"
        />
      </main>

      <!-- ASIDE: правая колонка — НЕ часть сетки новостей.
           Отдельный блок фиксированной ширины, стоит справа от main. -->
      <aside class="home__side">
        <WorldClockWidget />

        <QuickServicesWidget />

        <PhotosWidget />
      </aside>
    </div>

    <!-- НИЖНИЙ РЯД: 3 равные карточки под контентом, на всю ширину. -->
    <div class="home__bottom-row">
      <QuickLinksWidget />

      <MeetingsWidget />

      <BirthdaysWidget />
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
/* ════════════════════════════════════════════════════════════════════════════
   LAYOUT-АРХИТЕКТУРА (по референсу, НЕ единый grid на всю страницу):
   Page → Hero (над контентом)
        → Content (flex: main flex:1 + aside width:360px flex-shrink:0)
             → Main: featured + news header + NewsGrid (grid 3×N)
             → Aside: правая колонка, отдельный блок
        → Bottom row (grid 3 равные карточки)
   Правая колонка НЕ часть сетки новостей — это отдельный <aside> справа от main.
   ════════════════════════════════════════════════════════════════════════════ */

/* КОНТЕНТ: flex, не grid. main растягивается, aside фиксирован. */
.home__content {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 16px;
}

/* MAIN (новости): flex:1, занимает всё оставшееся место. */
.home__main {
  flex: 1 1 0;
  min-width: 0; /* критично для flex-children с grid внутри */
}

/* ASIDE (правая колонка): фиксированная ширина ~360px, не сжимается.
   Отдельный блок — НЕ участвует в сетке новостей. */
.home__side {
  flex: 0 0 340px;
  width: 340px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  position: sticky;
  top: 16px;
}

/* НИЖНИЙ РЯД: карточки под контентом, на всю ширину.
   auto-fit — если часть виджетов скрыта (v-if: meetings/bookmarks/дни рождения),
   оставшиеся растягиваются без пустых колонок-дыр. align-items: start — карточки
   НЕ растягиваются до высоты самой высокой (иначе короткие раздуются впустую). */
.home__bottom-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 14px;
  align-items: start;
}

.news-header { margin-bottom: 16px; }
.section__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  gap: 12px;
  flex-wrap: wrap;
}
.section__title {
  margin: 0;
  font-size: var(--fs-section-title, 28px); /* концепт: 28px */
  font-weight: 700;
  letter-spacing: -0.015em;
  color: var(--color-text);
}
.section__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* === Responsive === */
/* Средние десктопы (1366–1440): правая колонка чуть уже */
@media (max-width: 1440px) {
  .home__side { flex-basis: 340px; width: 340px; }
}
@media (max-width: 1366px) {
  .home__content { gap: 20px; }
  .home__side { flex-basis: 320px; width: 320px; }
  .section__title { font-size: 24px; }
}
/* Ниже 1024px — коллапс в одну колонку: aside уходит под main, sticky отключается */
@media (max-width: 1024px) {
  .home__content { flex-direction: column; }
  .home__side { position: static; width: 100%; flex-basis: auto; }
  .home__bottom-row { grid-template-columns: 1fr; }
}
@media (max-width: 1280px) and (min-width: 1025px) {
  /* На средних: нижний ряд — minmax сам свернёт в доступное число колонок */
}
</style>
