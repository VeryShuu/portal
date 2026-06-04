<template>
  <div>
    <div
      v-if="loading"
      class="article-wrap"
    >
      <n-skeleton
        text
        style="margin-bottom:16px;height:40px"
      />
      <n-skeleton
        text
        :repeat="6"
      />
    </div>

    <div
      v-else-if="article"
      class="article-outer"
    >
      <div class="article-back">
        <n-button
          quaternary
          size="small"
          class="back-btn"
          @click="router.push('/kb')"
        >
          <template #icon>
            <n-icon><ChevronBackOutline /></n-icon>
          </template>
          {{ t('common.back') }}
        </n-button>
      </div>

      <KbArticleHeader
        :article="article"
        @edit="router.push(`/kb/articles/${article.id}/edit`)"
        @manage-perms="showPermsModal = true"
        @delete="onDelete"
        @export="onExport"
      />

      <div class="article-page">
        <div class="article-main">
          <div
            class="article-body"
            v-html="renderedBody"
          />

          <KbArticleFeedback
            :helpful-count="article.helpful_count"
            :not-helpful-count="article.not_helpful_count"
            :user-feedback="article.user_feedback"
            @feedback="onFeedback"
          />

          <n-tabs
            v-model:value="activeTab"
            type="line"
            class="article-tabs"
          >
            <n-tab-pane
              name="comments"
              :tab="t('kb.comments') + ` (${commentTotal})`"
            >
              <KbArticleCommentsTab
                :article-id="article.id"
                @count-changed="(n: number) => (commentTotal = n)"
              />
            </n-tab-pane>

            <n-tab-pane
              v-if="article.version > 1"
              name="versions"
              :tab="t('kb.versions')"
            >
              <KbArticleVersionsTab
                :article-id="article.id"
                :current-version="article.version"
                :can-restore="canEdit"
                @diff="openDiff"
              />
            </n-tab-pane>

            <n-tab-pane
              v-if="!canEdit"
              name="suggest"
              :tab="t('kb.suggestEdit')"
            >
              <KbArticleSuggestTab :article-id="article.id" />
            </n-tab-pane>
          </n-tabs>
        </div>

        <aside
          v-show="showSidebar"
          class="article-sidebar"
        >
          <KbAttachmentsPanel
            :article-id="article.id"
            :can-upload="canEdit"
            @files-loaded="onFilesLoaded"
          />
        </aside>
      </div>
    </div>

    <div
      v-else
      class="article-wrap"
    >
      <EmptyState
        variant="default"
        :title="t('kb.notFound')"
        description=""
      />
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
import { ref, computed, onBeforeUnmount, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import { NTabs, NTabPane, NSkeleton, NButton, NIcon } from 'naive-ui'
import { ChevronBackOutline } from '@vicons/ionicons5'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import { useQueryClient } from '@tanstack/vue-query'
import { sanitizeKbHtml } from '@/utils/sanitize'
import { mdUnsafe as md } from '@/utils/markdown'
import { useLayoutHeader } from '../composables/useLayoutHeader'
import EmptyState from '../components/EmptyState.vue'
import KbArticleHeader from '../components/KbArticleHeader.vue'
import KbArticleFeedback from '../components/KbArticleFeedback.vue'
import KbArticleCommentsTab from '../components/KbArticleCommentsTab.vue'
import KbArticleVersionsTab from '../components/KbArticleVersionsTab.vue'
import KbArticleSuggestTab from '../components/KbArticleSuggestTab.vue'
import KbAttachmentsPanel from '../components/KbAttachmentsPanel.vue'
import KbPermissionsModal from '../components/KbPermissionsModal.vue'
import KbVersionDiffModal from '../components/KbVersionDiffModal.vue'
import {
  exportArticlePdf, exportArticleDocx,
  type KbArticle,
} from '../api/kb'
import { useKbArticleQuery, useDeleteKbArticleMutation, useSubmitKbFeedbackMutation } from '../queries/kb'
import { queryKeys } from '../queries/keys'

const router = useRouter()
const route = useRoute()
const { t } = useI18n()
const message = useMessage()
const { confirm } = useConfirmDialog()
const { setHeader, clearHeader } = useLayoutHeader()
const queryClient = useQueryClient()
const deleteKbArticleMutation = useDeleteKbArticleMutation()

const articleId = computed(() => route.params.id as string)

const { data: article, isLoading: loading } = useKbArticleQuery(articleId)

watch(article, (a) => {
  if (a) {
    setHeader(a.title)
  }
}, { immediate: true })

const activeTab = ref('comments')
const commentTotal = ref(0)
const showPermsModal = ref(false)
const diffModal = ref({ show: false, v1: 1, v2: 1 })
const sidebarFilesCount = ref<number | null>(null)

const canEdit = computed(() => {
  const perm = article.value?.user_permission
  return !!perm && ['editor', 'manager'].includes(perm)
})

const showSidebar = computed(() => {
  if (canEdit.value) return true
  return sidebarFilesCount.value !== null && sidebarFilesCount.value > 0
})

const renderedBody = computed(() => {
  if (!article.value) return ''
  return sanitizeKbHtml(md.render(article.value.body))
})

function onFilesLoaded(count: number) {
  sidebarFilesCount.value = count
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
    await deleteKbArticleMutation.mutateAsync(articleId.value)
    router.push('/kb')
  } catch {
    message.error(t('common.error'))
  }
}

function openDiff(v1: number, v2: number) {
  diffModal.value = { show: true, v1, v2 }
}

const submitFeedbackMutation = useSubmitKbFeedbackMutation()

async function onFeedback(isHelpful: boolean) {
  try {
    await submitFeedbackMutation.mutateAsync({
      articleId: articleId.value,
      isHelpful,
    })
    message.success(t('common.saved'))
  } catch {
    message.error(t('common.error'))
  }
}

onBeforeUnmount(() => {
  clearHeader()
})
</script>

<style scoped>
.article-wrap {
  max-width: var(--content-standard);
  margin: 0 auto;
}

.article-outer {
  max-width: var(--content-standard);
  margin: 0 auto;
}

.article-back {
  margin-bottom: 16px;
}

.article-page {
  display: flex;
  gap: 28px;
  align-items: flex-start;
}

.article-main {
  flex: 1;
  min-width: 0;
}

.article-sidebar {
  width: 270px;
  flex-shrink: 0;
  position: sticky;
  top: 16px;
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

.article-body :deep(div[data-callout]) {
  border-radius: 6px;
  padding: 12px 16px;
  margin: 1em 0;
  border-left: 4px solid;
}
.article-body :deep(div[data-callout][data-type="info"]) {
  background: #e8f4ff;
  border-color: #2080f0;
  color: #1a3a5c;
}
.article-body :deep(div[data-callout][data-type="warning"]) {
  background: #fff8e6;
  border-color: #f0a020;
  color: #5c3a00;
}
.article-body :deep(div[data-callout][data-type="tip"]) {
  background: #edfaef;
  border-color: #18a058;
  color: #0d3d1f;
}
.article-body :deep(div[data-callout][data-type="danger"]) {
  background: #fff0f0;
  border-color: #d03050;
  color: #5c0d1a;
}

.article-body :deep(details) {
  border: 1px solid var(--n-border-color, #e0e0e6);
  border-radius: 6px;
  padding: 0;
  margin: 1em 0;
  overflow: hidden;
}
.article-body :deep(details > summary) {
  padding: 10px 14px;
  font-weight: 600;
  cursor: pointer;
  background: var(--n-table-header-color, #f5f5f7);
  user-select: none;
  list-style: none;
  display: flex;
  align-items: center;
  gap: 6px;
}
.article-body :deep(details > summary::-webkit-details-marker) {
  display: none;
}
.article-body :deep(details > summary::before) {
  content: '▶';
  font-size: 10px;
  transition: transform 0.2s;
  display: inline-block;
}
.article-body :deep(details[open] > summary::before) {
  transform: rotate(90deg);
}
.article-body :deep(details > *:not(summary)) {
  padding: 12px 14px;
}

.article-body :deep(mark) {
  background: #fff3a0;
  padding: 0 2px;
  border-radius: 2px;
}
.article-body :deep(ul[data-type="taskList"]) {
  list-style: none;
  padding-left: 0;
}
.article-body :deep(ul[data-type="taskList"] li) {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin: 2px 0;
}
.article-body :deep(ul[data-type="taskList"] li > label) {
  margin-top: 2px;
  user-select: none;
  flex: 0 0 auto;
}
.article-body :deep(ul[data-type="taskList"] li > div) {
  flex: 1 1 auto;
  min-width: 0;
}
.article-body :deep(ul[data-type="taskList"] li[data-checked="true"] > div) {
  text-decoration: line-through;
  color: var(--color-text-muted);
}

.article-tabs { margin-bottom: 40px; }

@media (max-width: 768px) {
  .article-page {
    flex-direction: column;
  }

  .article-sidebar {
    width: 100%;
    position: static;
  }
}
</style>
