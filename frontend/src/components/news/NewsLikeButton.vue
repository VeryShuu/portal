<template>
  <button
    type="button"
    class="news-like"
    :class="{ 'news-like--active': liked, 'news-like--compact': compact }"
    :disabled="pending"
    :aria-pressed="liked"
    :title="liked ? t('news.likes.liked') : t('news.likes.like')"
    @click="onClick"
  >
    <n-icon
      class="news-like__icon"
      :class="{ 'news-like__icon--pop': popping }"
      :size="compact ? 15 : 17"
    >
      <Heart v-if="liked" />
      <HeartOutline v-else />
    </n-icon>
    <span class="news-like__count">{{ likeCount }}</span>
  </button>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { NIcon } from 'naive-ui'
import { Heart, HeartOutline } from '@vicons/ionicons5'
import { useToggleNewsLikeMutation } from '../../queries/news'

const props = defineProps<{
  newsId: string
  likeCount: number
  liked: boolean
  compact?: boolean
}>()

const { t } = useI18n()
const toggle = useToggleNewsLikeMutation()
const pending = ref(false)
const popping = ref(false)

async function onClick() {
  if (pending.value) return
  const next = !props.liked
  if (next) {
    popping.value = true
    window.setTimeout(() => (popping.value = false), 280)
  }
  pending.value = true
  try {
    await toggle.mutateAsync({ id: props.newsId, liked: next })
  } finally {
    pending.value = false
  }
}
</script>

<style scoped>
.news-like {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border: 1px solid var(--color-border);
  border-radius: 999px;
  background: var(--color-surface);
  color: var(--color-text-muted);
  font-size: 13px;
  font-weight: 600;
  line-height: 1;
  cursor: pointer;
  transition: color 0.15s ease, border-color 0.15s ease, background 0.15s ease;
}

.news-like:hover:not(:disabled) {
  border-color: var(--color-brand-red);
  color: var(--color-brand-red);
}

.news-like:disabled {
  cursor: default;
  opacity: 0.7;
}

.news-like--active {
  border-color: var(--color-brand-red);
  background: var(--color-brand-red-soft);
  color: var(--color-brand-red);
}

.news-like--compact {
  padding: 3px 9px;
  font-size: 12px;
}

.news-like__icon {
  display: inline-flex;
}

.news-like__icon--pop {
  animation: like-pop 0.28s ease;
}

.news-like__count {
  font-variant-numeric: tabular-nums;
}

@keyframes like-pop {
  0% { transform: scale(1); }
  40% { transform: scale(1.35); }
  100% { transform: scale(1); }
}
</style>
