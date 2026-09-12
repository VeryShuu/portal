<template>
  <div class="directum-tab branding-wrap">
    <DirectumSettings />

    <section class="branding-section">
      <h3 class="branding-section__title">
        {{ t('admin.directum.actions.title') }}
      </h3>
      <p class="branding-section__hint">
        {{ t('admin.directum.actions.hint') }}
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
          {{ t('admin.directum.actions.runNow') }}
        </n-button>
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

    <DirectumRuns />
  </div>
</template>

<script setup lang="ts">
import { defineAsyncComponent, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NIcon, useMessage } from 'naive-ui'
import { SyncOutline } from '@vicons/ionicons5'
import { parseApiError } from '../../../utils/parseApiError'
import { fetchDirectumRuns, runDirectumNow } from '../../../api/directum'
import { useQueryClient } from '@tanstack/vue-query'
import { queryKeys } from '../../../queries/keys'

const { t } = useI18n()
const message = useMessage()
const qc = useQueryClient()

const DirectumSettings = defineAsyncComponent(
  () => import('../../../components/admin/DirectumSettings.vue'),
)
const DirectumRuns = defineAsyncComponent(
  () => import('../../../components/admin/DirectumRuns.vue'),
)

const running = ref(false)
const runResult = ref<{ ok: boolean; title: string; detail?: string } | null>(null)

async function invalidateRuns() {
  await qc.invalidateQueries({ queryKey: queryKeys.directum.all })
}

async function onRunNow() {
  running.value = true
  runResult.value = null
  try {
    // Запоминаем ID последнего прогона — чтобы выйти из опроса, как только
    // появится свежий (прогон выполняется в воркере за секунды).
    const before = await fetchDirectumRuns({ limit: 1, offset: 0 })
    const lastIdBefore = before.items[0]?.id ?? 0

    const res = await runDirectumNow()
    runResult.value = {
      ok: true,
      title: t('admin.directum.actions.runQueued'),
      detail: res.job_id ? `job_id: ${res.job_id}` : undefined,
    }
    message.info(t('admin.directum.actions.runQueuedHint'))
    const appeared = await pollRuns(90_000, 3_000, lastIdBefore)
    if (!appeared) {
      // Прогон не появился за 90с — вместо вечной «зелёной» очереди честно
      // предупреждаем (скип-причины run-строку не создают).
      runResult.value = { ok: false, title: t('admin.directum.actions.runTimeout') }
    }
  } catch (e) {
    runResult.value = { ok: false, title: parseApiError(e, t) }
  } finally {
    running.value = false
  }
}

async function pollRuns(deadlineMs: number, intervalMs: number, lastIdBefore = 0) {
  const deadline = Date.now() + deadlineMs
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, intervalMs))
    await invalidateRuns()
    const latest = await fetchDirectumRuns({ limit: 1, offset: 0 })
    const newestId = latest.items[0]?.id ?? 0
    if (newestId > lastIdBefore) return true
  }
  return false
}
</script>

<style scoped>
@import '../admin-tabs.css';

/* Directum-вкладка: таблица истории прогонов шире формы — расширяем до полной
   доступной ширины контента (как erp_sync). */
.directum-tab {
  max-width: none;
}
</style>
