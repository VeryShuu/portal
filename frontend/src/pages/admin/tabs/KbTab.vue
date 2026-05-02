<template>
  <div class="branding-wrap">

    <div class="branding-section">
      <div class="branding-section__title">{{ t('admin.kb.exportTitle') }}</div>
      <div class="branding-section__hint">{{ t('admin.kb.exportHint') }}</div>
      <div class="email-actions" style="margin-top:16px">
        <n-button @click="onExportKbVault">
          ⬇ {{ t('admin.kb.exportVaultBtn') }}
        </n-button>
      </div>
    </div>

    <div class="branding-section">
      <div class="branding-section__title">{{ t('admin.kb.importTitle') }}</div>
      <div class="branding-section__hint">{{ t('admin.kb.importHint') }}</div>

      <div class="branding-fields" style="margin-top:16px">
        <n-form-item :label="t('kb.import.strategy')" style="margin-bottom:0">
          <n-select
            v-model:value="adminKbImportStrategy"
            :options="adminKbStrategyOptions"
            size="medium"
            style="max-width:320px"
          />
        </n-form-item>
      </div>

      <n-tabs v-model:value="adminKbImportTab" type="line" size="small" style="margin-top:16px">
        <n-tab-pane name="md" :tab="t('kb.import.fromMd')">
          <div
            class="drop-zone"
            :class="{ 'drop-zone--over': adminMdDragOver }"
            @dragover.prevent="adminMdDragOver = true"
            @dragleave="adminMdDragOver = false"
            @drop.prevent="onAdminDropMd"
            @click="adminMdFileRef?.click()"
          >
            <div v-if="adminMdFile">📄 {{ adminMdFile.name }}</div>
            <div v-else>{{ t('kb.import.fromMd') }} — {{ t('kb.import.dropOrClick') }}</div>
          </div>
          <input ref="adminMdFileRef" type="file" accept=".md" style="display:none" @change="onAdminMdFileChange" />
        </n-tab-pane>

        <n-tab-pane name="vault" :tab="t('kb.import.fromVault')">
          <div
            class="drop-zone"
            :class="{ 'drop-zone--over': adminZipDragOver }"
            @dragover.prevent="adminZipDragOver = true"
            @dragleave="adminZipDragOver = false"
            @drop.prevent="onAdminDropZip"
            @click="adminZipFileRef?.click()"
          >
            <div v-if="adminZipFile">📦 {{ adminZipFile.name }}</div>
            <div v-else>{{ t('kb.import.fromVault') }} — {{ t('kb.import.dropOrClick') }}</div>
          </div>
          <input ref="adminZipFileRef" type="file" accept=".zip" style="display:none" @change="onAdminZipFileChange" />
        </n-tab-pane>
      </n-tabs>

      <div v-if="adminKbImporting" class="import-progress" style="margin-top:16px">
        <n-progress type="line" :percentage="100" status="info" processing :indicator-placement="'inside'">
          {{ t('kb.import.inProgress') }}
        </n-progress>
      </div>

      <div v-if="adminKbImportResult" class="import-result" style="margin-top:16px;padding:12px 16px;background:var(--color-surface);border:1px solid var(--color-border);border-radius:8px">
        <div style="font-size:14px;margin-bottom:4px;color:#2e7d32">✅ {{ t('kb.import.created') }}: {{ adminKbImportResult.created }}</div>
        <div style="font-size:14px;margin-bottom:4px">🔄 {{ t('kb.import.updated') }}: {{ adminKbImportResult.updated }}</div>
        <div style="font-size:14px;margin-bottom:4px;color:var(--color-text-muted)">⏭ {{ t('kb.import.skipped') }}: {{ adminKbImportResult.skipped }}</div>
        <template v-if="adminKbImportResult.errors.length">
          <div style="font-size:14px;margin-top:8px;color:#d32f2f">❌ {{ t('kb.import.errors') }}:</div>
          <div v-for="e in adminKbImportResult.errors" :key="e" style="font-size:12px;color:#d32f2f;padding:2px 0 2px 12px">{{ e }}</div>
        </template>
      </div>

      <div class="email-actions" style="margin-top:16px">
        <n-button
          type="primary"
          :loading="adminKbImporting"
          :disabled="adminKbImportTab === 'md' ? !adminMdFile : !adminZipFile"
          @click="runAdminKbImport"
        >
          {{ t('kb.import.title') }}
        </n-button>
      </div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NTabs, NTabPane, NSelect, NFormItem, NProgress, useMessage } from 'naive-ui'
import { importMarkdownFile, importVaultZip, exportKbVault, type ImportResult } from '../../../api/kb'

const { t } = useI18n()
const message = useMessage()

const adminKbImportTab = ref<'md' | 'vault'>('vault')
const adminKbImportStrategy = ref<'skip' | 'overwrite' | 'create_new'>('skip')
const adminKbImporting = ref(false)
const adminKbImportResult = ref<ImportResult | null>(null)

const adminMdFile = ref<File | null>(null)
const adminZipFile = ref<File | null>(null)
const adminMdDragOver = ref(false)
const adminZipDragOver = ref(false)
const adminMdFileRef = ref<HTMLInputElement | null>(null)
const adminZipFileRef = ref<HTMLInputElement | null>(null)

const adminKbStrategyOptions = computed(() => [
  { label: t('kb.import.skip'), value: 'skip' },
  { label: t('kb.import.overwrite'), value: 'overwrite' },
  { label: t('kb.import.createNew'), value: 'create_new' },
])

function onAdminMdFileChange(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0]
  if (f) adminMdFile.value = f
}

function onAdminZipFileChange(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0]
  if (f) adminZipFile.value = f
}

function onAdminDropMd(e: DragEvent) {
  adminMdDragOver.value = false
  const f = e.dataTransfer?.files[0]
  if (f && f.name.endsWith('.md')) adminMdFile.value = f
}

function onAdminDropZip(e: DragEvent) {
  adminZipDragOver.value = false
  const f = e.dataTransfer?.files[0]
  if (f && f.name.endsWith('.zip')) adminZipFile.value = f
}

async function runAdminKbImport() {
  adminKbImporting.value = true
  adminKbImportResult.value = null
  try {
    if (adminKbImportTab.value === 'md' && adminMdFile.value) {
      adminKbImportResult.value = await importMarkdownFile(adminMdFile.value)
    } else if (adminKbImportTab.value === 'vault' && adminZipFile.value) {
      adminKbImportResult.value = await importVaultZip(adminZipFile.value, adminKbImportStrategy.value)
    }
    adminMdFile.value = null
    adminZipFile.value = null
    message.success(t('admin.kb.importSuccess'))
  } catch (e: unknown) {
    message.error(e instanceof Error ? e.message : t('errors.generic'))
  } finally {
    adminKbImporting.value = false
  }
}

function onExportKbVault() {
  exportKbVault()
}
</script>

<style scoped>
@import '../admin-tabs.css';
</style>
