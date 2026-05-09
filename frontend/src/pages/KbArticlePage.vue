<template>
  <div>
    <div v-if="loading" class="article-wrap">
      <n-skeleton text style="margin-bottom:16px;height:40px" />
      <n-skeleton text :repeat="6" />
    </div>

    <div v-else-if="article" class="article-wrap">
      <!-- Шапка -->
      <div class="article-header">
        <div class="article-header__top">
          <span class="article-status" :class="`article-status--${article.status}`">
            {{ t(`kb.status.${article.status}`, article.status) }}
          </span>
          <div class="article-actions">
            <n-button v-if="article.user_permission && ['editor','manager'].includes(article.user_permission)" size="small" @click="router.push(`/kb/articles/${article.id}/edit`)">
              {{ t('common.edit') }}
            </n-button>
            <n-button v-if="canManagePerms" size="small" @click="showPermsModal = true">
              🔐 {{ t('kb.permissions.manage') }}
            </n-button>
            <n-dropdown :options="exportOptions" @select="onExport">
              <n-button size="small">{{ t('kb.export.title') }} ▾</n-button>
            </n-dropdown>
            <n-button v-if="auth.isAdmin" size="small" type="error" @click="onDelete">
              {{ t('common.delete') }}
            </n-button>
          </div>
        </div>

        <h1 class="article-title">{{ article.title }}</h1>

        <div class="article-meta">
          <span v-if="article.created_by">
            {{ t('kb.author') }}: <strong>{{ article.created_by.full_name }}</strong>
          </span>
          <span>{{ t('kb.updated') }}: {{ formatDate(article.updated_at, locale) }}</span>
          <span>👁 {{ article.view_count }}</span>
          <span>v{{ article.version }}</span>
        </div>

        <div v-if="article.tags.length" class="article-tags">
          <span v-for="tag in article.tags" :key="tag.id" class="kb-tag">{{ tag.name }}</span>
        </div>
      </div>

      <!-- Тело статьи -->
      <div class="article-body" v-html="renderedBody" />

      <!-- Обратная связь -->
      <div class="article-feedback">
        <span class="article-feedback__label">{{ t('kb.feedbackLabel') }}</span>
        <button
          class="feedback-btn"
          :class="{ 'feedback-btn--active': article.user_feedback === true }"
          @click="onFeedback(true)"
        >
          👍 {{ article.helpful_count }}
        </button>
        <button
          class="feedback-btn"
          :class="{ 'feedback-btn--active': article.user_feedback === false }"
          @click="onFeedback(false)"
        >
          👎 {{ article.not_helpful_count }}
        </button>
      </div>

      <!-- Вкладки: комментарии / версии / предложить правку -->
      <n-tabs v-model:value="activeTab" type="line" class="article-tabs">
        <n-tab-pane name="comments" :tab="t('kb.comments') + ` (${commentTotal})`">
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
                  @click="onDeleteComment(c.id)"
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
            <n-button type="primary" :loading="commentLoading" @click="onSubmitComment">
              {{ t('kb.submitComment') }}
            </n-button>
          </div>
        </n-tab-pane>

        <n-tab-pane name="versions" :tab="t('kb.versions')">
          <div class="versions-list">
            <div v-for="v in versions" :key="v.id" class="version-item">
              <div class="version-item__header">
                <span class="version-item__num">v{{ v.version }}</span>
                <span class="version-item__by">{{ v.changed_by?.full_name ?? '—' }}</span>
                <span class="version-item__date">{{ formatDate(v.created_at, locale) }}</span>
                <span v-if="v.change_comment" class="version-item__comment">{{ v.change_comment }}</span>
                <n-button
                  size="tiny"
                  @click="openDiff(v.version, article.version)"
                >
                  {{ t('kb.diff.compare') }}
                </n-button>
                <n-button
                  v-if="article.user_permission && ['editor','manager'].includes(article.user_permission) && v.version !== article.version"
                  size="tiny"
                  @click="onRestoreVersion(v.version)"
                >
                  {{ t('kb.restoreVersion') }}
                </n-button>
              </div>
            </div>
            <EmptyState v-if="!versions.length" variant="default" :title="t('kb.noVersions')" description="" />
          </div>
        </n-tab-pane>

        <n-tab-pane v-if="!article.user_permission || !['editor','manager'].includes(article.user_permission)" name="suggest" :tab="t('kb.suggestEdit')">
          <div class="suggest-form">
            <p class="suggest-form__hint">{{ t('kb.suggestHint') }}</p>
            <RichEditor v-model="suggestBody" :placeholder="t('kb.suggestPlaceholder')" />
            <n-input
              v-model:value="suggestComment"
              :placeholder="t('kb.suggestCommentPlaceholder')"
              style="margin-top:8px"
            />
            <n-button type="primary" :loading="suggestLoading" @click="onSuggest">
              {{ t('kb.submitSuggest') }}
            </n-button>
          </div>
        </n-tab-pane>
      </n-tabs>

      <!-- Вложения -->
      <KbAttachmentsPanel
        :article-id="article.id"
        :can-upload="!!article.user_permission && ['editor','manager'].includes(article.user_permission)"
        style="margin-top:24px"
      />
    </div>

    <div v-else class="article-wrap">
      <EmptyState variant="default" :title="t('kb.notFound')" description="" />
    </div>



    <KbPermissionsModal
      v-if="article"
      v-model="showPermsModal"
      resource-type="article"
      :resource-id="article.id"
      :inherit-permissions="article.inherit_permissions"
      @inherit-changed="(v: boolean) => queryClient.setQueryData<KbArticle>(queryKeys.kb.article(articleId), (old) => old ? { ...old, inherit_permissions: v } : old)"
    />

    <KbVersionDiffModal
      v-if="diffModal.show && article"
      v-model="diffModal.show"
      :article-id="article.id"
      :v1="diffModal.v1"
      :v2="diffModal.v2"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import {
  NButton, NDropdown, NTabs, NTabPane, NInput, NSkeleton,
} from 'naive-ui'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import { useQueryClient } from '@tanstack/vue-query'
import { sanitizeHtml } from '@/utils/sanitize'
import { mdSafe as md } from '@/utils/markdown'
import { formatDate } from '@/utils/formatDate'
import { useLayoutHeader } from '../composables/useLayoutHeader'
import EmptyState from '../components/EmptyState.vue'
import RichEditor from '../components/RichEditor.vue'
import KbAttachmentsPanel from '../components/KbAttachmentsPanel.vue'
import KbPermissionsModal from '../components/KbPermissionsModal.vue'
import KbVersionDiffModal from '../components/KbVersionDiffModal.vue'
import { useAuthStore } from '../stores/auth'
import {
  fetchComments, createComment, deleteComment,
  fetchVersions, restoreVersion, submitFeedback, suggestEdit,
  exportArticlePdf, exportArticleDocx,
  deleteArticle,
  type KbArticle, type KbComment, type KbVersion,
} from '../api/kb'
import { useKbArticleQuery } from '../queries/kb'
import { queryKeys } from '../queries/keys'
import { trackArticleView } from '../composables/useRecentArticles'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const { t, locale } = useI18n()
const message = useMessage()
const { confirm } = useConfirmDialog()
const { setHeader, clearHeader } = useLayoutHeader()
const queryClient = useQueryClient()

const articleId = computed(() => route.params.id as string)

const { data: article, isLoading: loading } = useKbArticleQuery(articleId)

watch(article, (a) => {
  if (a) {
    setHeader(a.title)
    trackArticleView({ id: a.id, title: a.title })
  }
})

const activeTab = ref('comments')

const comments = ref<KbComment[]>([])
const commentTotal = ref(0)
const commentLoading = ref(false)
const newComment = ref('')

const versions = ref<KbVersion[]>([])
const suggestBody = ref('')
const suggestComment = ref('')
const suggestLoading = ref(false)
const showPermsModal = ref(false)
const diffModal = ref({ show: false, v1: 1, v2: 1 })

const canManagePerms = computed(() => article.value?.user_permission === 'manager')



const renderedBody = computed(() => {
  if (!article.value) return ''
  return sanitizeHtml(md.render(article.value.body))
})

const exportOptions = computed(() => [
  { label: t('kb.export.pdf'), key: 'pdf' },
  { label: t('kb.export.docx'), key: 'docx' },
  { label: t('kb.export.md'), key: 'md' },
])

function canDeleteComment(c: KbComment) {
  if (auth.isAdmin) return true
  return c.author?.id === auth.user?.id
}

async function loadComments() {
  try {
    const res = await fetchComments(articleId.value, { limit: 50 })
    comments.value = res.items
    commentTotal.value = res.total
  } catch {
    message.error(t('common.error'))
  }
}

async function loadVersions() {
  try {
    const res = await fetchVersions(articleId.value, { limit: 50 })
    versions.value = res.items
  } catch {
    message.error(t('common.error'))
  }
}

async function onFeedback(isHelpful: boolean) {
  if (!article.value) return
  try {
    const res = await submitFeedback(articleId.value, isHelpful)
    queryClient.setQueryData<KbArticle>(queryKeys.kb.article(articleId.value), (old) =>
      old ? { ...old, helpful_count: res.helpful_count, not_helpful_count: res.not_helpful_count, user_feedback: res.user_feedback } : old,
    )
  } catch {
    message.error(t('common.error'))
  }
}

async function onSubmitComment() {
  if (!newComment.value.trim()) return
  commentLoading.value = true
  try {
    await createComment(articleId.value, newComment.value.trim())
    newComment.value = ''
    await loadComments()
  } catch {
    message.error(t('common.error'))
  } finally {
    commentLoading.value = false
  }
}

async function onDeleteComment(commentId: string) {
  try {
    await deleteComment(articleId.value, commentId)
    await loadComments()
  } catch {
    message.error(t('common.error'))
  }
}

async function onRestoreVersion(versionNum: number) {
  try {
    const restored = await restoreVersion(articleId.value, versionNum)
    queryClient.setQueryData(queryKeys.kb.article(articleId.value), restored)
    message.success(t('kb.versionRestored'))
    await loadVersions()
  } catch {
    message.error(t('common.error'))
  }
}

async function onSuggest() {
  if (!suggestBody.value.trim()) return
  suggestLoading.value = true
  try {
    await suggestEdit(articleId.value, { body: suggestBody.value, comment: suggestComment.value || undefined })
    suggestBody.value = ''
    suggestComment.value = ''
    message.success(t('kb.suggestSent'))
  } catch {
    message.error(t('common.error'))
  } finally {
    suggestLoading.value = false
  }
}

function onExport(key: string) {
  if (key === 'pdf') exportArticlePdf(articleId.value)
  else if (key === 'docx') exportArticleDocx(articleId.value)
  else if (key === 'md') window.open(`/api/v1/kb/articles/${articleId.value}/export/md`, '_blank', 'noopener,noreferrer')
}

async function onDelete() {
  const ok = await confirm({
    title: t('kb.deleteTitle'),
    content: t('kb.deleteConfirm'),
    positiveText: t('common.delete'),
    negativeText: t('common.cancel'),
  })
  if (!ok) return
  try {
    await deleteArticle(articleId.value)
    router.push('/kb')
  } catch {
    message.error(t('common.error'))
  }
}

function openDiff(v1: number, v2: number) {
  diffModal.value = { show: true, v1, v2 }
}

onMounted(async () => {
  await loadComments()
  await loadVersions()
})

watch(articleId, async () => {
  await loadComments()
  await loadVersions()
})

onBeforeUnmount(() => {
  clearHeader()
})
</script>

<style scoped>
.article-wrap {
  max-width: 900px;
  margin: 0 auto;
}

.article-header {
  margin-bottom: 32px;
  padding-bottom: 24px;
  border-bottom: 1px solid var(--color-border);
}

.article-header__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 8px;
}

.article-status {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  padding: 3px 10px;
  border-radius: var(--radius-pill);
}
.article-status--published { background: #e8f5e9; color: #2e7d32; }
.article-status--draft { background: #fff3e0; color: #e65100; }
.article-status--archived { background: var(--color-border); color: var(--color-text-muted); }

.article-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.article-title {
  margin: 0 0 12px;
  font-size: 32px;
  font-weight: 800;
  line-height: 1.2;
  color: var(--color-text);
  letter-spacing: -0.02em;
}

.article-meta {
  display: flex;
  gap: 16px;
  font-size: 13px;
  color: var(--color-text-muted);
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.article-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.kb-tag {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: var(--radius-pill);
  background: color-mix(in srgb, var(--color-brand-sky) 12%, transparent);
  color: var(--color-brand-sky);
}

.article-body {
  font-size: 16px;
  line-height: 1.75;
  color: var(--color-text);
  margin-bottom: 40px;
}
.article-body :deep(h1),
.article-body :deep(h2),
.article-body :deep(h3) { font-weight: 700; margin-top: 1.5em; margin-bottom: 0.5em; }
.article-body :deep(h2) { font-size: 22px; }
.article-body :deep(h3) { font-size: 18px; }
.article-body :deep(code) { background: var(--color-border); padding: 2px 5px; border-radius: 3px; font-size: 14px; }
.article-body :deep(pre) { background: var(--color-border); padding: 16px; border-radius: var(--radius-md); overflow-x: auto; }
.article-body :deep(blockquote) { border-left: 3px solid var(--color-brand-sky); margin: 0; padding-left: 16px; color: var(--color-text-muted); }
.article-body :deep(table) { border-collapse: collapse; width: 100%; margin: 16px 0; }
.article-body :deep(th),
.article-body :deep(td) { border: 1px solid var(--color-border); padding: 8px 12px; }
.article-body :deep(a) { color: var(--color-brand-sky); text-decoration: underline; }

.article-feedback {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 32px;
  padding: 16px 20px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
}

.article-feedback__label {
  font-size: 14px;
  color: var(--color-text-muted);
  margin-right: 4px;
}

.feedback-btn {
  font-size: 16px;
  padding: 6px 14px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-pill);
  background: none;
  cursor: pointer;
  transition: all var(--t-fast);
  font-family: inherit;
}
.feedback-btn:hover { border-color: var(--color-brand-sky); }
.feedback-btn--active { background: var(--color-brand-sky); color: #fff; border-color: var(--color-brand-sky); }

.article-tabs { margin-bottom: 40px; }

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

.versions-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.version-item {
  padding: 12px 16px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

.version-item__header {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 13px;
  flex-wrap: wrap;
}

.version-item__num {
  font-weight: 700;
  font-size: 14px;
}

.version-item__comment {
  color: var(--color-text-muted);
  font-style: italic;
}

.suggest-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.suggest-form__hint {
  margin: 0;
  font-size: 14px;
  color: var(--color-text-muted);
}
</style>
