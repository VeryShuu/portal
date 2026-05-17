<template>
  <div class="article-header">
    <div class="article-header__top">
      <span
        class="article-status"
        :class="`article-status--${article.status}`"
      >
        {{ t(`kb.status.${article.status}`, article.status) }}
      </span>
      <div class="article-actions">
        <n-button
          v-if="article.user_permission && ['editor','manager'].includes(article.user_permission)"
          size="small"
          @click="$emit('edit')"
        >
          {{ t('common.edit') }}
        </n-button>
        <n-button
          v-if="canManagePerms"
          size="small"
          @click="$emit('manage-perms')"
        >
          🔐 {{ t('kb.permissions.manage') }}
        </n-button>
        <n-dropdown
          :options="exportOptions"
          @select="(key: string) => $emit('export', key)"
        >
          <n-button size="small">
            {{ t('kb.export.title') }} ▾
          </n-button>
        </n-dropdown>
        <n-button
          v-if="auth.isAdmin"
          size="small"
          type="error"
          @click="$emit('delete')"
        >
          {{ t('common.delete') }}
        </n-button>
      </div>
    </div>

    <h1 class="article-title">
      {{ article.title }}
    </h1>

    <div class="article-meta">
      <span v-if="article.created_by">
        {{ t('kb.author') }}: <strong>{{ article.created_by.full_name }}</strong>
      </span>
      <span>{{ t('kb.updated') }}: {{ formatDate(article.updated_at, locale) }}</span>
      <span>👁 {{ article.view_count }}</span>
      <span>v{{ article.version }}</span>
    </div>

    <div
      v-if="article.tags.length"
      class="article-tags"
    >
      <span
        v-for="tag in article.tags"
        :key="tag.id"
        class="kb-tag"
      >{{ tag.name }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NDropdown } from 'naive-ui'
import { formatDate } from '@/utils/formatDate'
import { useAuthStore } from '../stores/auth'
import type { KbArticle } from '../api/kb'

const props = defineProps<{
  article: KbArticle
}>()

defineEmits<{
  (e: 'edit'): void
  (e: 'manage-perms'): void
  (e: 'delete'): void
  (e: 'export', key: string): void
}>()

const { t, locale } = useI18n()
const auth = useAuthStore()

const canManagePerms = computed(() => props.article.user_permission === 'manager')

const exportOptions = computed(() => [
  { label: t('kb.export.pdf'), key: 'pdf' },
  { label: t('kb.export.docx'), key: 'docx' },
  { label: t('kb.export.md'), key: 'md' },
])
</script>

<style scoped>
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
</style>
