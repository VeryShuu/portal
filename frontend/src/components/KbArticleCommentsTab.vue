<template>
  <div>
    <div class="comments-list">
      <div v-for="c in comments" :key="c.id" class="comment">
        <div class="comment__header">
          <strong>{{ c.is_deleted ? t('kb.deletedComment') : (c.author?.full_name ?? '—') }}</strong>
          <span class="comment__date">{{ formatDate(c.created_at, locale) }}</span>
          <n-button
            v-if="!c.is_deleted && canDeleteComment(c)"
            size="tiny"
            type="error"
            text
            @click="remove(c.id)"
          >
            {{ t('common.delete') }}
          </n-button>
        </div>
        <p class="comment__body">{{ c.is_deleted ? `[${t('kb.deletedComment')}]` : c.body }}</p>
      </div>
      <EmptyState v-if="!comments.length" variant="default" :title="t('kb.noComments')" description="" />
    </div>

    <div class="comment-form">
      <n-input
        v-model:value="newComment"
        type="textarea"
        :placeholder="t('kb.commentPlaceholder')"
        :autosize="{ minRows: 2, maxRows: 6 }"
      />
      <n-button type="primary" :loading="submitting" @click="submit">
        {{ t('kb.submitComment') }}
      </n-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { toRef, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NInput } from 'naive-ui'
import { formatDate } from '@/utils/formatDate'
import EmptyState from './EmptyState.vue'
import { useAuthStore } from '../stores/auth'
import { useKbArticleComments } from '../composables/useKbArticleComments'
import type { KbComment } from '../api/kb'

const props = defineProps<{ articleId: string }>()

const emit = defineEmits<{
  (e: 'count-changed', total: number): void
}>()

const { t, locale } = useI18n()
const auth = useAuthStore()

const { comments, total, submitting, newComment, submit, remove } =
  useKbArticleComments(toRef(props, 'articleId'))

watch(total, (v) => emit('count-changed', v), { immediate: true })

function canDeleteComment(c: KbComment) {
  if (auth.isAdmin) return true
  return c.author?.id === auth.user?.id
}
</script>

<style scoped>
.comments-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-bottom: 20px;
}

.comment {
  padding: 14px 16px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

.comment__header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
  font-size: 13px;
  flex-wrap: wrap;
}

.comment__date { color: var(--color-text-muted); }

.comment__body {
  margin: 0;
  font-size: 15px;
  line-height: 1.6;
  color: var(--color-text);
}

.comment-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
</style>
