<template>
  <section
    v-if="bookmarks.length"
    class="widget"
  >
    <div class="widget__header">
      <h3 class="widget__title">
        {{ t('home.sections.quickLinks') }}
      </h3>
      <n-button
        text
        size="tiny"
        @click="router.push('/links?tab=bookmarks')"
      >
        {{ t('home.sections.allBookmarks') }}
      </n-button>
    </div>

    <!-- Быстрые ссылки (ТЗ п.6): список пользовательских закладок.
         Каждая — отдельная строка с иконкой-стрелкой. Пусто → блок скрыт (v-if выше). -->
    <ul class="quick-links-list">
      <li
        v-for="bm in visible"
        :key="bm.id"
      >
        <a
          :href="bm.url"
          class="quick-link"
          :target="isExternal(bm.url) ? '_blank' : undefined"
          :rel="isExternal(bm.url) ? 'noopener noreferrer' : undefined"
          @click="onNavigate(bm, $event)"
        >
          <span
            class="quick-link__bullet"
            aria-hidden="true"
          />
          <span class="quick-link__title">{{ bm.title }}</span>
          <n-icon
            :size="14"
            class="quick-link__arrow"
          >
            <ArrowForwardOutline />
          </n-icon>
        </a>
      </li>
    </ul>

    <!-- Декоративный полупрозрачный силуэт исследовательского судна (концепт).
         Не интерактивный, чисто фоновая арктическая атрибутика МАГЭ. -->
    <svg
      class="quick-links-decor"
      viewBox="0 0 120 40"
      aria-hidden="true"
    >
      <path
        d="M5 28 L95 28 L88 36 L12 36 Z M30 28 L30 18 L75 18 L82 28 Z M40 18 L40 8 L55 8 L55 18"
        fill="none"
        stroke="currentColor"
        stroke-width="1.5"
        stroke-linejoin="round"
      />
    </svg>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NIcon } from 'naive-ui'
import { ArrowForwardOutline } from '@vicons/ionicons5'
import { useRouter } from 'vue-router'
import { useLinksStore } from '@/stores/links'
import type { Bookmark } from '@/api/links'

const { t } = useI18n()
const router = useRouter()
const linksStore = useLinksStore()

// Лимит строк; остальные — через «Все закладки».
const VISIBLE_LIMIT = 5

// Defensive: store может быть замокан минимально в тестах (без поля bookmarks).
const bookmarks = computed(() => linksStore.bookmarks ?? [])
const visible = computed(() => bookmarks.value.slice(0, VISIBLE_LIMIT))

// Внутренний путь (начинается с /) → router; внешний URL — новая вкладка.
function isExternal(url: string): boolean {
  return /^https?:\/\//i.test(url)
}

function onNavigate(bm: Bookmark, e: MouseEvent) {
  if (!isExternal(bm.url)) {
    e.preventDefault()
    void router.push(bm.url)
  }
}

onMounted(() => {
  // Виджет сам подгружает закладки, если ещё не загружены (как PhotosWidget).
  // Defensive guards: store может быть замокан минимально в тестах.
  if (!(linksStore.bookmarks ?? []).length && !linksStore.loadingBookmarks && linksStore.loadBookmarks) {
    void linksStore.loadBookmarks()
  }
})
</script>

<style scoped>
.widget {
  position: relative;
  overflow: hidden;
  background: var(--color-mage-card, var(--color-surface));
  border: 1px solid var(--color-mage-border, var(--color-border));
  border-radius: var(--radius-card, var(--radius-lg));
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

.quick-links-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
}
.quick-links-list > li + li {
  border-top: 1px solid var(--color-mage-border, var(--color-border));
}
.quick-link {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 4px;
  text-decoration: none;
  color: var(--color-mage-text, var(--color-text));
  font-size: 14px;
  border-radius: var(--radius-sm);
  transition: background var(--t-fast), color var(--t-fast);
}
.quick-link:hover {
  background: color-mix(in srgb, var(--color-mage-secondary, #2f6cb5) 8%, transparent);
}
.quick-link__bullet {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-mage-secondary, var(--color-brand-sky));
  flex-shrink: 0;
}
.quick-link__title {
  flex: 1;
  min-width: 0;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.quick-link__arrow {
  flex-shrink: 0;
  color: var(--color-mage-text-secondary, var(--color-text-muted));
  opacity: 0.6;
}
.quick-link:hover .quick-link__arrow {
  opacity: 1;
}
/* Декоративный силуэт судна в правом нижнем углу (концепт) */
.quick-links-decor {
  position: absolute;
  right: 10px;
  bottom: 6px;
  width: 100px;
  height: 34px;
  color: var(--color-mage-secondary, #2f6cb5);
  opacity: 0.08;
  pointer-events: none;
}
</style>
