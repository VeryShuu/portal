/**
 * DirectumTab.vue: композиция вкладки (настройки + «Запустить сейчас» + история).
 *
 * Проверяется: mount всей композиции с реальными дочерними компонентами
 * (их зависимости — queries/naive-ui — замоканы), run-now флоу (fetch before →
 * enqueue → поллинг до нового run), баннер результата, ошибка запуска.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NButton: {
    template: '<button class="n-button" :loading="loading" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'loading', 'disabled', 'size'],
    emits: ['click'],
  },
  NIcon: { template: '<i><slot /></i>' },
  NInput: {
    template: '<input :value="value ?? \'\'" :placeholder="placeholder ?? \'\'" @input="$emit(\'update:value\', $event.target.value)" />',
    props: ['value', 'placeholder', 'type', 'showPasswordOn', 'inputProps'],
    emits: ['update:value'],
  },
  NInputNumber: {
    template: '<input type="number" :value="value ?? \'\'" @input="$emit(\'update:value\', Number($event.target.value))" />',
    props: ['value', 'min', 'max', 'step'],
    emits: ['update:value'],
  },
  NForm: { template: '<form><slot /></form>', props: ['labelPlacement', 'showFeedback'] },
  NFormItem: { template: '<div class="n-form-item"><slot /><slot name="feedback" /></div>', props: ['label'] },
  NSpin: { template: '<div><slot /></div>', props: ['show'] },
  NSwitch: {
    template: '<input type="checkbox" class="n-switch" :checked="value" @change="$emit(\'update:value\', $event.target.checked)" />',
    props: ['value'],
    emits: ['update:value'],
  },
  NTag: { template: '<span class="n-tag"><slot /></span>', props: ['type', 'size', 'bordered'] },
  NDataTable: { template: '<div class="n-data-table" />', props: ['columns', 'data', 'loading', 'pagination', 'remote', 'rowKey', 'size', 'striped'] },
  NSelect: { template: '<div class="n-select" />', props: ['value', 'options', 'multiple', 'clearable', 'placeholder'], emits: ['update:value'] },
  useMessage: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}))

const invalidateQueries = vi.fn()
vi.mock('@tanstack/vue-query', () => ({
  useQueryClient: () => ({ invalidateQueries }),
}))

// Реальные DirectumSettings/DirectumRuns монтируются как есть — их данные
// замоканы на уровне queries. Async-фабрика: динамический import('vue') —
// статический реэкспорт из hoisted-фабрики падает на TDZ.
vi.mock('../../src/queries/directum', async () => {
  const { ref } = await import('vue')
  const settings = ref({
    enabled: true,
    base_url: 'https://sed.mage.ru/Integration/odata',
    auth_username: 'PDC1\\svc',
    password_set: true,
    configured: true,
    overdue_run_hours: [],
    expected_interval_days: 2,
    notify_emails: null,
    overdue_enabled: true,
    updated_at: null,
  })
  const runs = ref({
    items: [
      {
        id: 3,
        triggered_by: 'cron',
        started_at: '2026-08-17T09:00:00+03:00',
        finished_at: null,
        status: 'success',
        tasks_total: 1,
        performers_total: 1,
        users_notified: 1,
        users_skipped_opt_in: 0,
        users_unmatched: 0,
        users_ambiguous: 0,
        errors: 0,
        report: {},
      },
    ],
    total: 1,
  })
  return {
    useDirectumSettingsQuery: () => ({ data: settings, isLoading: ref(false) }),
    usePutDirectumSettingsMutation: () => ({
      mutateAsync: vi.fn().mockResolvedValue({}),
      isPending: ref(false),
    }),
    useDirectumRunsQuery: () => ({
      data: runs,
      isLoading: ref(false),
      refetch: vi.fn(),
    }),
  }
})

const runDirectumNow = vi.fn()
const fetchDirectumRuns = vi.fn()
vi.mock('../../src/api/directum', () => ({
  runDirectumNow: (...a: unknown[]) => runDirectumNow(...a),
  fetchDirectumRuns: (...a: unknown[]) => fetchDirectumRuns(...a),
  // DirectumSettings импортирует тест-подключение — экспорт обязан существовать.
  testDirectumConnection: () => Promise.resolve({ ok: true, detail: 'ok' }),
}))

import DirectumTab from '../../src/pages/admin/tabs/DirectumTab.vue'

async function clickRun(wrapper: ReturnType<typeof mount>) {
  await wrapper.find('.email-actions button').trigger('click')
  await flushPromises()
}

describe('DirectumTab', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('монтирует композицию: секция действий с кнопкой запуска', async () => {
    const wrapper = mount(DirectumTab, { global: { plugins: [i18n] } })
    await flushPromises()
    // Async-дети (настройки/история) резолвятся лениво; здесь проверяем
    // собственную разметку вкладки — секция действий и кнопка запуска.
    expect(wrapper.find('.email-actions button').exists()).toBe(true)
    expect(wrapper.text()).toContain('admin.directum.actions.runNow')
    expect(wrapper.text()).toContain('admin.directum.actions.title')
  })

  it('run-now: поллинг до появления нового прогона', async () => {
    vi.useFakeTimers()
    try {
      fetchDirectumRuns
        .mockResolvedValueOnce({ items: [{ id: 5 }], total: 1 }) // «до запуска»
        .mockResolvedValue({ items: [{ id: 9 }], total: 1 }) // в поллинге
      runDirectumNow.mockResolvedValue({ status: 'queued', job_id: 'directum:run:1' })

      const wrapper = mount(DirectumTab, { global: { plugins: [i18n] } })
      await flushPromises()
      await wrapper.find('.email-actions button').trigger('click')
      // Поллинг спит по 3с — прокручиваем первую итерацию виртуальным таймером.
      await vi.advanceTimersByTimeAsync(3_500)
      await flushPromises()

      expect(runDirectumNow).toHaveBeenCalledTimes(1)
      const limited = fetchDirectumRuns.mock.calls.filter(
        ([p]) => (p as { limit?: number }).limit === 1,
      )
      expect(limited.length).toBeGreaterThanOrEqual(2)
      expect(invalidateQueries).toHaveBeenCalled()
      const banner = wrapper.find('.kc-test-result')
      expect(banner.exists()).toBe(true)
      expect(banner.text()).toContain('directum:run:1')
    } finally {
      vi.useRealTimers()
    }
  })

  it('run-now ошибка: красный баннер с текстом ошибки', async () => {
    fetchDirectumRuns.mockResolvedValue({ items: [], total: 0 })
    runDirectumNow.mockRejectedValue({ data: { detail: 'creds' } })

    const wrapper = mount(DirectumTab, { global: { plugins: [i18n] } })
    await flushPromises()
    await clickRun(wrapper)  // clickRun кликает .email-actions button

    await flushPromises()
    expect(wrapper.find('.kc-test-result--fail').exists()).toBe(true)
  })

  it('run-now таймаут: прогон не появился за 90с — предупреждение вместо зелёной очереди', async () => {
    vi.useFakeTimers()
    try {
      // Новый прогон так и не появляется (id не растёт).
      fetchDirectumRuns.mockResolvedValue({ items: [{ id: 5 }], total: 1 })
      runDirectumNow.mockResolvedValue({ status: 'queued', job_id: 'directum:run:2' })

      const wrapper = mount(DirectumTab, { global: { plugins: [i18n] } })
      await flushPromises()
      await wrapper.find('.email-actions button').trigger('click')
      // Прокручиваем все 90 секунд поллинга виртуальными таймерами.
      await vi.advanceTimersByTimeAsync(95_000)
      await flushPromises()

      const banner = wrapper.find('.kc-test-result--fail')
      expect(banner.exists()).toBe(true)
      expect(banner.text()).toContain('runTimeout')
    } finally {
      vi.useRealTimers()
    }
  })
})
