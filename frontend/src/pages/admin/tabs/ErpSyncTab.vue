<template>
  <div class="erp-sync-tab branding-wrap">
    <ErpSyncSettings />

    <section class="branding-section">
      <h3 class="branding-section__title">
        {{ t('admin.erpSync.actions.title') }}
      </h3>
      <p class="branding-section__hint">
        {{ t('admin.erpSync.actions.hint') }}
      </p>

      <div class="email-actions">
        <n-button
          type="primary"
          :loading="running"
          :disabled="!mailboxConfigured"
          @click="onRunNow"
        >
          <template #icon>
            <n-icon><SyncOutline /></n-icon>
          </template>
          {{ t('admin.erpSync.actions.runNow') }}
        </n-button>

        <n-upload
          :show-file-list="false"
          :custom-request="onUploadFile"
          accept=".txt,.csv,.tsv,.xlsx,.xls"
        >
          <n-button :loading="uploading">
            <template #icon>
              <n-icon><CloudUploadOutline /></n-icon>
            </template>
            {{ t('admin.erpSync.actions.uploadFile') }}
          </n-button>
        </n-upload>
      </div>

      <div
        v-if="runResult"
        class="kc-test-result"
        :class="runResult.ok ? 'kc-test-result--ok' : 'kc-test-result--fail'"
      >
        <div class="kc-test-result__title">
          {{ runResult.title }}
        </div>
        <div
          v-if="runResult.detail"
          class="kc-test-result__details"
        >
          {{ runResult.detail }}
        </div>
      </div>
    </section>

    <ErpSyncRuns />
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NIcon, NUpload, useMessage, type UploadCustomRequestOptions } from 'naive-ui'
import { CloudUploadOutline, SyncOutline } from '@vicons/ionicons5'
import { parseApiError } from '../../../utils/parseApiError'
import { importErpSyncFile, runErpSyncNow } from '../../../api/erpSync'
import { useErpSyncSettingsQuery } from '../../../queries/erpSync'
import { useQueryClient } from '@tanstack/vue-query'
import { queryKeys } from '../../../queries/keys'

const { t } = useI18n()
const message = useMessage()
const qc = useQueryClient()

const ErpSyncSettings = defineAsyncComponent(
  () => import('../../../components/admin/ErpSyncSettings.vue'),
)
const ErpSyncRuns = defineAsyncComponent(
  () => import('../../../components/admin/ErpSyncRuns.vue'),
)

const { data: settings } = useErpSyncSettingsQuery()
const mailboxConfigured = computed(
  () => Boolean(settings.value?.imap_host && settings.value?.imap_username),
)

const running = ref(false)
const uploading = ref(false)
const runResult = ref<{ ok: boolean; title: string; detail?: string } | null>(null)

async function invalidateRuns() {
  await qc.invalidateQueries({ queryKey: queryKeys.erpSync.all })
}

async function onRunNow() {
  running.value = true
  runResult.value = null
  try {
    const res = await runErpSyncNow()
    runResult.value = {
      ok: true,
      title: t('admin.erpSync.actions.runQueued'),
      detail: res.job_id ? `job_id: ${res.job_id}` : undefined,
    }
    message.info(t('admin.erpSync.actions.runQueuedHint'))
    // Polling runs history: импорт выполнится в воркере за секунды-минуты.
    // Опрашиваем раз в 3с до 90с; таблица истории обновится.
    await pollRuns(90_000, 3_000)
  } catch (e) {
    runResult.value = { ok: false, title: parseApiError(e, t) }
  } finally {
    running.value = false
  }
}

async function onUploadFile({ file }: UploadCustomRequestOptions) {
  if (!file.file) return
  uploading.value = true
  runResult.value = null
  try {
    const res = await importErpSyncFile(file.file)
    runResult.value = {
      ok: true,
      title: t('admin.erpSync.actions.uploadDone', { id: res.run_id ?? '?' }),
    }
    message.success(t('admin.erpSync.actions.uploadDone', { id: res.run_id ?? '?' }))
    await invalidateRuns()
  } catch (e) {
    runResult.value = { ok: false, title: parseApiError(e, t) }
    message.error(parseApiError(e, t))
  } finally {
    uploading.value = false
  }
}

async function pollRuns(deadlineMs: number, intervalMs: number) {
  const deadline = Date.now() + deadlineMs
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, intervalMs))
    await invalidateRuns()
  }
}
</script>

<style scoped>
@import '../admin-tabs.css';
</style>
