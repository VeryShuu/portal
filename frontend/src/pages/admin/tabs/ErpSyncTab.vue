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

    <section class="branding-section">
      <h3 class="branding-section__title">
        {{ t('admin.erpSync.absencesActions.title') }}
      </h3>
      <p class="branding-section__hint">
        {{ t('admin.erpSync.absencesActions.hint') }}
      </p>

      <div class="email-actions">
        <n-button
          type="primary"
          :loading="absRunning"
          @click="onAbsencesRunNow"
        >
          <template #icon>
            <n-icon><SyncOutline /></n-icon>
          </template>
          {{ t('admin.erpSync.actions.runNow') }}
        </n-button>

        <n-upload
          :show-file-list="false"
          :custom-request="onAbsencesUploadFile"
          accept=".txt,.csv,.tsv,.xlsx,.xls"
        >
          <n-button :loading="absUploading">
            <template #icon>
              <n-icon><CloudUploadOutline /></n-icon>
            </template>
            {{ t('admin.erpSync.actions.uploadFile') }}
          </n-button>
        </n-upload>
      </div>

      <div
        v-if="absRunResult"
        class="kc-test-result"
        :class="absRunResult.ok ? 'kc-test-result--ok' : 'kc-test-result--fail'"
      >
        <div class="kc-test-result__title">
          {{ absRunResult.title }}
        </div>
        <div
          v-if="absRunResult.detail"
          class="kc-test-result__details"
        >
          {{ absRunResult.detail }}
        </div>
      </div>
    </section>

    <ErpSyncRuns />
  </div>
</template>

<script setup lang="ts">
import { defineAsyncComponent, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NIcon, NUpload, useMessage, type UploadCustomRequestOptions } from 'naive-ui'
import { CloudUploadOutline, SyncOutline } from '@vicons/ionicons5'
import { parseApiError } from '../../../utils/parseApiError'
import {
  importErpSyncFile,
  runErpSyncNow,
  fetchErpSyncRuns,
  runErpAbsencesNow,
  importErpAbsencesFile,
  fetchErpAbsencesRuns,
} from '../../../api/erpSync'
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

const running = ref(false)
const uploading = ref(false)
const runResult = ref<{ ok: boolean; title: string; detail?: string } | null>(null)

// Действия для потока отсутствий (отдельный state от дней рождения).
const absRunning = ref(false)
const absUploading = ref(false)
const absRunResult = ref<{ ok: boolean; title: string; detail?: string } | null>(null)

async function invalidateRuns() {
  await qc.invalidateQueries({ queryKey: queryKeys.erpSync.all })
}

async function onRunNow() {
  running.value = true
  runResult.value = null
  try {
    // Запоминаем ID последнего run'а до запуска — чтобы выйти из опроса сразу,
    // как только появится свежий (а не докручивать фиксированные 90 секунд).
    const before = await fetchErpSyncRuns({ limit: 1, offset: 0 })
    const lastIdBefore = before.items[0]?.id ?? 0

    const res = await runErpSyncNow()
    runResult.value = {
      ok: true,
      title: t('admin.erpSync.actions.runQueued'),
      detail: res.job_id ? `job_id: ${res.job_id}` : undefined,
    }
    message.info(t('admin.erpSync.actions.runQueuedHint'))
    // Polling runs history: импорт выполнится в воркере за секунды-минуты.
    // Опрашиваем раз в 3с до 90с; выходим сразу при появлении нового run'а.
    await pollRuns(90_000, 3_000, lastIdBefore)
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

async function pollRuns(deadlineMs: number, intervalMs: number, lastIdBefore = 0) {
  const deadline = Date.now() + deadlineMs
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, intervalMs))
    await invalidateRuns()
    // Ранний выход: в истории появился свежий run → импорт выполнен,
    // больше крутить спиннер не нужно.
    const latest = await fetchErpSyncRuns({ limit: 1, offset: 0 })
    const newestId = latest.items[0]?.id ?? 0
    if (newestId > lastIdBefore) break
  }
}

// ── Поток отсутствий: mailbox-trigger + multipart-upload (клоны onRunNow/onUploadFile)
async function onAbsencesRunNow() {
  absRunning.value = true
  absRunResult.value = null
  try {
    const before = await fetchErpAbsencesRuns({ limit: 1, offset: 0 })
    const lastIdBefore = before.items[0]?.id ?? 0

    const res = await runErpAbsencesNow()
    absRunResult.value = {
      ok: true,
      title: t('admin.erpSync.actions.runQueued'),
      detail: res.job_id ? `job_id: ${res.job_id}` : undefined,
    }
    message.info(t('admin.erpSync.actions.runQueuedHint'))
    await pollAbsencesRuns(90_000, 3_000, lastIdBefore)
  } catch (e) {
    absRunResult.value = { ok: false, title: parseApiError(e, t) }
  } finally {
    absRunning.value = false
  }
}

async function onAbsencesUploadFile({ file }: UploadCustomRequestOptions) {
  if (!file.file) return
  absUploading.value = true
  absRunResult.value = null
  try {
    const res = await importErpAbsencesFile(file.file)
    absRunResult.value = {
      ok: true,
      title: t('admin.erpSync.actions.uploadDone', { id: res.run_id ?? '?' }),
    }
    message.success(t('admin.erpSync.actions.uploadDone', { id: res.run_id ?? '?' }))
    await invalidateRuns()
  } catch (e) {
    absRunResult.value = { ok: false, title: parseApiError(e, t) }
    message.error(parseApiError(e, t))
  } finally {
    absUploading.value = false
  }
}

async function pollAbsencesRuns(deadlineMs: number, intervalMs: number, lastIdBefore = 0) {
  const deadline = Date.now() + deadlineMs
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, intervalMs))
    await invalidateRuns()
    const latest = await fetchErpAbsencesRuns({ limit: 1, offset: 0 })
    const newestId = latest.items[0]?.id ?? 0
    if (newestId > lastIdBefore) break
  }
}
</script>

<style scoped>
@import '../admin-tabs.css';

/* ERP-вкладка: контент шире, чем форма-вкладки (branding-wrap 640px), — здесь
   таблица истории импортов и двухколоночная форма настроек. Расширяем до полной
   доступной ширины контента, не ломая остальные админ-вкладки. */
.erp-sync-tab {
  max-width: none;
}
</style>
