<template>
  <div
    class="home u-page-wrap u-page-wrap--wide"
    style="--page-gutter: clamp(8px, 1.5vw, 20px);"
  >
    <PortalBanner />

    <!-- HERO — отдельный блок над контентом, на всю ширину основной колонки.
         Не входит ни в какой grid. -->
    <HeroBlock />

    <!-- Featured (pinned) новость — над контентом, на всю ширину (если есть). -->
    <HomeFeaturedNewsSection
      :loading-news="loadingNews"
      :pinned="pinned"
      :categories-map="categoriesMap"
      @news-click="goToNews"
    />

    <!-- КОНТЕНТ: flex (НЕ grid). main flex:1 + aside фиксированной ширины.
         Кнопки «Создать/Смотреть все» убраны с главной — их нет в шапке.
         6-я плитка-ячейка «Смотреть все» живёт внутри NewsGrid. -->
    <div class="home__content">
      <!-- MAIN: сетка новостей + дни рождения -->
      <main class="home__main">
        <HomeNewsGrid
          :loading-news="loadingNews"
          :regular="regular"
          :categories-map="categoriesMap"
          @news-click="goToNews"
        />

        <!-- Дни рождения — горизонтальной полосой ПОД новостями, на всю ширину
             main-колонки. Карусель (слайдер 3×2) разворачивается в длину здесь,
             а не сжата в узком aside. -->
        <BirthdaysWidget />
      </main>

      <!-- ASIDE: компактные виджеты справа (часы перенесены в Hero). -->
      <aside class="home__side">
        <QuickServicesWidget />

        <MeetingsWidget />

        <PhotosWidget />

        <QuickLinksWidget />
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import HeroBlock from '../components/HeroBlock.vue'
import BirthdaysWidget from '../components/widgets/BirthdaysWidget.vue'
import PhotosWidget from '../components/widgets/PhotosWidget.vue'
import MeetingsWidget from '../components/widgets/MeetingsWidget.vue'
import QuickLinksWidget from '../components/widgets/QuickLinksWidget.vue'
import PortalBanner from '../components/widgets/PortalBanner.vue'
import HomeFeaturedNewsSection from '../components/widgets/HomeFeaturedNewsSection.vue'
import HomeNewsGrid from '../components/widgets/HomeNewsGrid.vue'
import QuickServicesWidget from '../components/widgets/QuickServicesWidget.vue'
import { useHomeNews } from '../composables/useHomeNews'

const { loadingNews, pinned, regular, categoriesMap, goToNews } = useHomeNews()
</script>

<style scoped>
/* ════════════════════════════════════════════════════════════════════════════
   LAYOUT-АРХИТЕКТУРА: чистый 2-колоночный layout.
   Page → Hero (над контентом, на всю ширину)
        → Content (flex: main flex:1 + aside фиксирован)
             → Main: featured + news header + NewsGrid (grid 3×N)
             → Aside: единый поток всех виджетов (часы, встречи, сервисы,
               дни рождения, фото, закладки) — ничего не «витает» отдельно.
   ════════════════════════════════════════════════════════════════════════════ */

/* КОНТЕНТ: flex, не grid. main растягивается, aside фиксирован. */
.home__content {
  display: flex;
  align-items: flex-start;
  gap: 14px;
}

/* MAIN (новости + дни рождения): flex:1. Дни рождения — полосой под новостями. */
.home__main {
  flex: 1 1 0;
  min-width: 0;
}
.home__main > * + * {
  margin-top: 14px;
}

/* ASIDE: фиксированная ширина, единый поток виджетов.
   НЕ участвует в сетке новостей, НЕ sticky (нет визуального шума при скролле). */
.home__side {
  flex: 0 0 340px;
  width: 340px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* === Responsive === */
@media (max-width: 1440px) {
  .home__side { flex-basis: 320px; width: 320px; }
}
@media (max-width: 1366px) {
  .home__side { flex-basis: 300px; width: 300px; }
}
@media (max-width: 1024px) {
  .home__content { flex-direction: column; }
  .home__side { width: 100%; flex-basis: auto; }
}
</style>
