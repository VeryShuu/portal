<template>
  <section class="news-comments">
    <h2 class="news-comments__title">
      {{ t('news.comments.title') }}
      <span class="news-comments__count">{{ total }}</span>
    </h2>

    <div
      v-if="auth.isAuthenticated"
      class="news-comments__form"
    >
      <n-avatar
        round
        :size="40"
        :src="auth.user?.avatar_url ?? undefined"
        class="news-comments__avatar"
      >
        {{ myInitials }}
      </n-avatar>
      <div class="news-comments__form-body">
        <n-input
          v-model:value="newComment"
          type="textarea"
          :placeholder="t('news.comments.placeholder')"
          :autosize="{ minRows: 2, maxRows: 8 }"
          :maxlength="4000"
        />
        <div class="news-comments__form-actions">
          <n-button
            type="primary"
            :loading="submitting"
            :disabled="!newComment.trim()"
            @click="submit"
          >
            {{ t('news.comments.submit') }}
          </n-button>
        </div>
      </div>
    </div>

    <div
      v-if="comments.length"
      class="news-comments__list"
    >
      <NewsCommentItem
        v-for="c in comments"
        :key="c.id"
        :comment="c"
        :on-edit="edit"
        :on-remove="onRemove"
      />
    </div>
    <p
      v-else
      class="news-comments__empty"
    >
      {{ t('news.comments.empty') }}
    </p>
  </section>
</template>

<script setup lang="ts">
import { computed, toRef } from 'vue'
import { useI18n } from 'vue-i18n'
import { NAvatar, NButton, NInput, useDialog } from 'naive-ui'
import { useAuthStore } from '../../stores/auth'
import { useNewsComments } from '../../composables/useNewsComments'
import NewsCommentItem from './NewsCommentItem.vue'

const props = defineProps<{ newsId: string }>()

const { t } = useI18n()
const auth = useAuthStore()
const dialog = useDialog()

const { comments, total, submitting, newComment, submit, edit, remove } = useNewsComments(
  toRef(props, 'newsId'),
)

const myInitials = computed(() => {
  const name = auth.user?.full_name?.trim()
  if (!name) return '—'
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? '')
    .join('')
})

function onRemove(commentId: string) {
  dialog.warning({
    title: t('news.comments.confirmDelete'),
    positiveText: t('common.delete'),
    negativeText: t('common.cancel'),
    onPositiveClick: () => {
      remove(commentId)
    },
  })
}
</script>

<style scoped>
.news-comments {
  margin-top: 32px;
  padding-top: 24px;
  border-top: 1px solid var(--color-border);
}

.news-comments__title {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0 0 20px;
  font-size: 20px;
  font-weight: 600;
  color: var(--color-text);
}

.news-comments__count {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text-muted);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 999px;
  padding: 1px 10px;
}

.news-comments__form {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 24px;
}

.news-comments__avatar {
  flex-shrink: 0;
  background: var(--color-brand-navy, #1f3a5f);
}

.news-comments__form-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.news-comments__form-actions {
  display: flex;
  justify-content: flex-end;
}

.news-comments__list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.news-comments__empty {
  margin: 0;
  font-size: 15px;
  color: var(--color-text-muted);
}
</style>
