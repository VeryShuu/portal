<template>
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
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { NButton } from 'naive-ui'
import { useRecentKbArticles } from '../../pages/composables/useRecentKbArticles'

const router = useRouter()
const { t } = useI18n()
const { recentArticles } = useRecentKbArticles()
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
</style>
