<template>
  <n-modal
    :show="show"
    preset="card"
    :title="t('kb.import.title')"
    style="max-width:500px"
    @update:show="$emit('update:show', $event)"
  >
    <div class="import-wrap">
      <n-tabs
        v-model:value="importTab"
        type="line"
        size="small"
      >
        <n-tab-pane
          name="md"
          :tab="t('kb.import.fromMd')"
        >
          <div
            class="drop-zone"
            :class="{ 'drop-zone--over': mdDragOver }"
            role="button"
            tabindex="0"
            @dragover.prevent="mdDragOver = true"
            @dragleave="mdDragOver = false"
            @drop.prevent="onDropMd"
            @click="mdFileRef?.click()"
            @keydown.enter="mdFileRef?.click()"
          >
            <div v-if="mdFile">
              📄 {{ mdFile.name }}
            </div>
            <div v-else>
              {{ t('kb.import.fromMd') }} — перетащите или нажмите
            </div>
          </div>
          <input
            ref="mdFileRef"
            type="file"
            accept=".md"
            style="display:none"
            aria-label="Select Markdown file"
            @change="onMdFileChange"
          >
        </n-tab-pane>

        <n-tab-pane
          name="vault"
          :tab="t('kb.import.fromVault')"
        >
          <n-form-item :label="t('kb.import.strategy')">
            <n-select
              v-model:value="importStrategy"
              :options="strategyOptions"
              size="small"
              style="width:100%"
            />
          </n-form-item>
          <div
            class="drop-zone"
            :class="{ 'drop-zone--over': zipDragOver }"
            role="button"
            tabindex="0"
            @dragover.prevent="zipDragOver = true"
            @dragleave="zipDragOver = false"
            @drop.prevent="onDropZip"
            @click="zipFileRef?.click()"
            @keydown.enter="zipFileRef?.click()"
          >
            <div v-if="zipFile">
              📦 {{ zipFile.name }}
            </div>
            <div v-else>
              {{ t('kb.import.fromVault') }} — перетащите или нажмите
            </div>
          </div>
          <input
            ref="zipFileRef"
            type="file"
            accept=".zip"
            style="display:none"
            aria-label="Select ZIP archive"
            @change="onZipFileChange"
          >
        </n-tab-pane>
      </n-tabs>

      <div
        v-if="importing"
        class="import-progress"
      >
        <n-progress
          type="line"
          :percentage="100"
          status="info"
          processing
          :indicator-placement="'inside'"
        >
          {{ t('kb.import.inProgress') }}
        </n-progress>
      </div>

      <div
        v-if="importResult"
        class="import-result"
      >
        <div class="import-result__row import-result__created">
          ✅ {{ t('kb.import.created') }}: {{ importResult.created }}
        </div>
        <div class="import-result__row import-result__updated">
          🔄 {{ t('kb.import.updated') }}: {{ importResult.updated }}
        </div>
        <div class="import-result__row import-result__skipped">
          ⏭ {{ t('kb.import.skipped') }}: {{ importResult.skipped }}
        </div>
        <div
          v-if="importResult.errors.length"
          class="import-result__errors"
        >
          <div
            class="import-result__row"
            style="color:var(--error-color)"
          >
            ❌ {{ t('kb.import.errors') }}:
          </div>
          <div
            v-for="e in importResult.errors"
            :key="e"
            class="import-result__error-item"
          >
            {{ e }}
          </div>
        </div>
      </div>

      <div
        class="modal-actions"
        style="margin-top:16px"
      >
        <n-button @click="close">
          {{ t('common.close') }}
        </n-button>
        <n-button
          type="primary"
          :loading="importing"
          :disabled="importTab === 'md' ? !mdFile : !zipFile"
          @click="runImport"
        >
          {{ t('kb.import.submit') }}
        </n-button>
      </div>
    </div>
  </n-modal>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQueryClient } from '@tanstack/vue-query'
import { queryKeys } from '../queries/keys'
import {
  NButton,
  NFormItem,
  NModal,
  NProgress,
  NSelect,
  NTabs,
  NTabPane,
  useMessage,
} from 'naive-ui'
import {
  importMarkdownFile,
  importVaultZip,
  type ImportResult,
} from '../api/kb'

defineProps<{ show: boolean }>()

const emit = defineEmits<{
  'update:show': [v: boolean]
  imported: []
}>()

const { t } = useI18n()
const message = useMessage()
const qc = useQueryClient()

const importTab = ref<'md' | 'vault'>('md')
const importing = ref(false)
const importResult = ref<ImportResult | null>(null)

const mdFile = ref<File | null>(null)
const zipFile = ref<File | null>(null)
const mdDragOver = ref(false)
const zipDragOver = ref(false)
const mdFileRef = ref<HTMLInputElement | null>(null)
const zipFileRef = ref<HTMLInputElement | null>(null)

const importStrategy = ref<'skip' | 'overwrite' | 'create_new'>('skip')
const strategyOptions = computed(() => [
  { label: t('kb.import.skip'), value: 'skip' },
  { label: t('kb.import.overwrite'), value: 'overwrite' },
  { label: t('kb.import.createNew'), value: 'create_new' },
])

function onMdFileChange(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0]
  if (f) mdFile.value = f
}

function onZipFileChange(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0]
  if (f) zipFile.value = f
}

function onDropMd(e: DragEvent) {
  mdDragOver.value = false
  const f = e.dataTransfer?.files[0]
  if (f && f.name.endsWith('.md')) mdFile.value = f
}

function onDropZip(e: DragEvent) {
  zipDragOver.value = false
  const f = e.dataTransfer?.files[0]
  if (f && f.name.endsWith('.zip')) zipFile.value = f
}

function close() {
  mdFile.value = null
  zipFile.value = null
  importResult.value = null
  emit('update:show', false)
}

async function runImport() {
  importing.value = true
  importResult.value = null
  try {
    if (importTab.value === 'md' && mdFile.value) {
      importResult.value = await importMarkdownFile(mdFile.value)
    } else if (importTab.value === 'vault' && zipFile.value) {
      importResult.value = await importVaultZip(zipFile.value, importStrategy.value)
    }
    qc.invalidateQueries({ queryKey: queryKeys.kb.all })
    emit('imported')
  } catch (e: unknown) {
    message.error(e instanceof Error ? e.message : 'Ошибка импорта')
  } finally {
    importing.value = false
  }
}
</script>

<style scoped>
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 16px;
}

.drop-zone {
  border: 2px dashed var(--color-border);
  border-radius: var(--radius-lg);
  padding: 32px 16px;
  text-align: center;
  font-size: 14px;
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all var(--t-fast);
  margin-top: 8px;
}
.drop-zone:hover,
.drop-zone--over {
  border-color: var(--color-brand-sky);
  background: color-mix(in srgb, var(--color-brand-sky) 6%, transparent);
  color: var(--color-brand-sky);
}

.import-progress {
  margin-top: 16px;
}

.import-result {
  margin-top: 16px;
  padding: 12px 16px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}
.import-result__row {
  font-size: 14px;
  margin-bottom: 4px;
}
.import-result__errors {
  margin-top: 8px;
}
.import-result__error-item {
  font-size: 12px;
  color: var(--error-color, #d32f2f);
  padding: 2px 0 2px 12px;
}
</style>
