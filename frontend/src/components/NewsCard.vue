<template>
  <n-card
    class="news-card"
    :class="{ pinned: news.is_pinned }"
    hoverable
    @click="$emit('click', news.id)"
  >
    <template #header>
      <div class="card-header">
        <n-tag v-if="news.is_pinned" type="warning" size="small" round>
          {{ t('news.pinned') }}
        </n-tag>
        <n-tag v-if="news.category" size="small" round>{{ news.category }}</n-tag>
        <span class="status-badge" :class="news.status">{{ t(`news.status.${news.status}`) }}</span>
      </div>
    </template>

    <h3 class="news-title">{{ news.title }}</h3>

    <p class="news-excerpt">{{ excerpt }}</p>

    <template #footer>
      <div class="card-footer">
        <span class="meta">{{ formattedDate }}</span>
        <span class="views">
          <n-icon size="14"><EyeOutline /></n-icon>
          {{ news.view_count }}
        </span>
      </div>
    </template>
  </n-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NCard, NTag, NIcon } from 'naive-ui'
import { EyeOutline } from '@vicons/ionicons5'
import type { News } from '../api/news'

defineEmits<{ click: [id: string] }>()
const props = defineProps<{ news: News }>()
const { t } = useI18n()

const excerpt = computed(() => {
  const text = props.news.body.replace(/<[^>]*>/g, '').replace(/[#*_`>\[\]]/g, '').trim()
  return text.length > 180 ? text.slice(0, 180) + '...' : text
})

const formattedDate = computed(() => {
  const d = props.news.published_at ?? props.news.created_at
  return new Date(d).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })
})
</script>

<style scoped>
.news-card {
  cursor: pointer;
  transition: box-shadow .2s;
}
.news-card.pinned {
  border-left: 3px solid #f0a020;
}
.card-header {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.status-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  margin-left: auto;
}
.status-badge.published { background: #18a05820; color: #18a058; }
.status-badge.draft     { background: #88888820; color: #888; }
.status-badge.archived  { background: #d0302030; color: #d03020; }
.news-title {
  margin: 8px 0 6px;
  font-size: 16px;
  font-weight: 600;
  line-height: 1.3;
}
.news-excerpt {
  font-size: 14px;
  color: var(--n-text-color-2, #666);
  line-height: 1.5;
  margin: 0;
}
.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  color: #999;
}
.views {
  display: flex;
  align-items: center;
  gap: 4px;
}
</style>
