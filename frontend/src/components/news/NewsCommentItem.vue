<template>
  <div class="news-comment">
    <n-avatar
      round
      :size="40"
      :src="comment.author?.avatar_url ?? undefined"
      class="news-comment__avatar"
    >
      {{ initials }}
    </n-avatar>

    <div class="news-comment__body">
      <div class="news-comment__head">
        <strong class="news-comment__name">
          {{ comment.is_deleted ? '—' : (comment.author?.full_name ?? '—') }}
        </strong>
        <span
          class="news-comment__time"
          :title="absoluteTime"
        >
          {{ relativeTime }}
        </span>

        <div
          v-if="!comment.is_deleted && (canEdit || canDelete)"
          class="news-comment__actions"
        >
          <button
            v-if="canEdit && !editing"
            type="button"
            class="news-comment__action"
            @click="startEdit"
          >
            {{ t('news.comments.edit') }}
          </button>
          <button
            v-if="canDelete && !editing"
            type="button"
            class="news-comment__action news-comment__action--danger"
            @click="onDelete"
          >
            {{ t('common.delete') }}
          </button>
        </div>
      </div>

      <p
        v-if="comment.is_deleted"
        class="news-comment__text news-comment__text--deleted"
      >
        {{ t('news.comments.deleted') }}
      </p>

      <template v-else-if="editing">
        <n-input
          v-model:value="draft"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 8 }"
          :maxlength="4000"
        />
        <div class="news-comment__edit-actions">
          <n-button
            size="small"
            type="primary"
            :loading="saving"
            :disabled="!draft.trim()"
            @click="onSave"
          >
            {{ t('news.comments.save') }}
          </n-button>
          <n-button
            size="small"
            quaternary
            @click="cancelEdit"
          >
            {{ t('common.cancel') }}
          </n-button>
        </div>
      </template>

      <p
        v-else
        class="news-comment__text"
      >
        {{ comment.body }}
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { NAvatar, NButton, NInput } from 'naive-ui'
import { formatDate, formatRelativeTime } from '@/utils/formatDate'
import { useAuthStore } from '../../stores/auth'
import type { NewsComment } from '../../api/news'

const props = defineProps<{
  comment: NewsComment
  onEdit: (commentId: string, body: string) => Promise<boolean>
  onRemove: (commentId: string) => void
}>()

const { t, locale } = useI18n()
const auth = useAuthStore()

const editing = ref(false)
const saving = ref(false)
const draft = ref('')

const isAuthor = computed(() => props.comment.author?.id === auth.user?.id)
const canEdit = computed(() => isAuthor.value)
const canDelete = computed(() => auth.isAdmin || isAuthor.value)

const initials = computed(() => {
  const name = props.comment.author?.full_name?.trim()
  if (!name) return '—'
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? '')
    .join('')
})

const relativeTime = computed(() => formatRelativeTime(props.comment.created_at, locale.value))
const absoluteTime = computed(() => formatDate(props.comment.created_at, locale.value))

function startEdit() {
  draft.value = props.comment.body ?? ''
  editing.value = true
}

function cancelEdit() {
  editing.value = false
  draft.value = ''
}

async function onSave() {
  const body = draft.value.trim()
  if (!body) return
  saving.value = true
  try {
    const ok = await props.onEdit(props.comment.id, body)
    if (ok) editing.value = false
  } finally {
    saving.value = false
  }
}

function onDelete() {
  props.onRemove(props.comment.id)
}
</script>

<style scoped>
.news-comment {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.news-comment__avatar {
  flex-shrink: 0;
  background: var(--color-brand-navy, #1f3a5f);
}

.news-comment__body {
  flex: 1;
  min-width: 0;
  padding: 12px 14px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

.news-comment__head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
  font-size: 13px;
  flex-wrap: wrap;
}

.news-comment__name {
  color: var(--color-text);
}

.news-comment__time {
  color: var(--color-text-muted);
}

.news-comment__actions {
  display: flex;
  gap: 8px;
  margin-left: auto;
}

.news-comment__action {
  padding: 0;
  border: none;
  background: none;
  font-size: 13px;
  color: var(--color-text-muted);
  cursor: pointer;
  transition: color 0.15s ease;
}

.news-comment__action:hover {
  color: var(--color-brand-navy, #1f3a5f);
}

.news-comment__action--danger:hover {
  color: var(--color-brand-red, #d03050);
}

.news-comment__text {
  margin: 0;
  font-size: 15px;
  line-height: 1.6;
  color: var(--color-text);
  white-space: pre-wrap;
  word-break: break-word;
}

.news-comment__text--deleted {
  font-style: italic;
  color: var(--color-text-muted);
}

.news-comment__edit-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}
</style>
