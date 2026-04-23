<template>
  <n-modal v-model:show="show" preset="card" :title="diffTitle" style="max-width:900px; width:96vw">
    <div v-if="loading" class="diff-loading">
      <n-spin size="medium" />
    </div>
    <div v-else-if="diff" class="diff-wrap">
      <div class="diff-stats">
        <span class="diff-added">+{{ diff.stats.added }}</span>
        <span class="diff-removed">-{{ diff.stats.removed }}</span>
      </div>
      <div v-if="!diff.hunks.length" class="diff-identical">{{ t('kb.diff.identical') }}</div>
      <div v-else class="diff-hunks">
        <div v-for="(hunk, hi) in diff.hunks" :key="hi" class="diff-hunk">
          <div class="diff-hunk-header">{{ hunk.header }}</div>
          <div
            v-for="(line, li) in hunk.lines"
            :key="li"
            class="diff-line"
            :class="{
              'diff-line--added': line.startsWith('+'),
              'diff-line--removed': line.startsWith('-'),
              'diff-line--context': !line.startsWith('+') && !line.startsWith('-'),
            }"
          >
            <span class="diff-line-content">{{ line }}</span>
          </div>
        </div>
      </div>
    </div>
    <div v-else class="diff-error">{{ t('kb.diff.loadError') }}</div>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NModal, NSpin } from 'naive-ui'
import { $fetch } from 'ofetch'

const props = defineProps<{
  modelValue: boolean
  articleId: string
  v1: number
  v2: number
}>()

const emit = defineEmits<{
  'update:modelValue': [v: boolean]
}>()

const { t } = useI18n()

const show = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

interface DiffHunk { header: string; lines: string[] }
interface DiffData { hunks: DiffHunk[]; stats: { added: number; removed: number } }

const diff = ref<DiffData | null>(null)
const loading = ref(false)

const diffTitle = computed(() => `${t('kb.diff.title')} v${props.v1} → v${props.v2}`)

watch(() => props.modelValue, (v) => {
  if (v) loadDiff()
})

async function loadDiff() {
  loading.value = true
  diff.value = null
  try {
    diff.value = await $fetch<DiffData>(
      `/api/v1/kb/articles/${props.articleId}/versions/${props.v1}/diff/${props.v2}`,
      { credentials: 'include' }
    )
  } catch {
    diff.value = null
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.diff-loading { display: flex; justify-content: center; padding: 32px; }
.diff-error, .diff-identical { text-align: center; color: var(--n-text-color-3, #999); padding: 24px; }
.diff-stats { display: flex; gap: 12px; margin-bottom: 12px; font-size: 14px; font-weight: 600; }
.diff-added { color: #18a058; }
.diff-removed { color: #d03050; }
.diff-hunks { font-family: monospace; font-size: 13px; overflow-x: auto; }
.diff-hunk { margin-bottom: 12px; border: 1px solid var(--n-border-color, #e0e0e6); border-radius: 6px; overflow: hidden; }
.diff-hunk-header { background: #f0f4ff; color: #666; padding: 4px 10px; font-size: 12px; }
.diff-line { padding: 1px 10px; white-space: pre; }
.diff-line--added { background: #ecfdf5; color: #059669; }
.diff-line--removed { background: #fff1f2; color: #e11d48; }
.diff-line--context { color: var(--n-text-color-1, #333); }
</style>
