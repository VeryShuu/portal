/**
 * BulkApproveReport.vue: постоянный отчёт массового согласования — счётчики,
 * строки «документ → результат → причина», тип по исходу, dismiss.
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NAlert: {
    template:
      '<div class="n-alert" :data-type="type"><slot /><button class="alert-close" @click="$emit(\'close\')" /></div>',
    props: ['type', 'showIcon', 'closable'],
    emits: ['close'],
  },
  NIcon: { template: '<i class="n-icon"><slot /></i>' },
}))

vi.mock('@vicons/ionicons5', () => ({
  CheckmarkCircleOutline: { template: '<i class="icon-ok" />' },
  CloseCircleOutline: { template: '<i class="icon-fail" />' },
}))

import BulkApproveReport from '../../src/components/approvals/BulkApproveReport.vue'

const rows = [
  { uuid: 'a', label: 'УП-1', sub: 'ООО Ромашка', ok: true, message: 'Согласовано' },
  {
    uuid: 'b',
    label: 'УП-2',
    sub: '',
    ok: false,
    message: 'ERP недоступна — документ не обрабатывался',
  },
]

describe('BulkApproveReport.vue', () => {
  it('part success: warning, иконки ok/fail, причина отказа, dismiss', async () => {
    const w = mount(BulkApproveReport, {
      props: { approved: 1, failed: 1, rows },
      global: { plugins: [i18n] },
    })
    expect(w.find('.n-alert').attributes('data-type')).toBe('warning')
    expect(w.text()).toContain('УП-1')
    expect(w.text()).toContain('ООО Ромашка')
    expect(w.text()).toContain('Согласовано')
    expect(w.text()).toContain('ERP недоступна — документ не обрабатывался')
    expect(w.findAll('.icon-ok').length).toBe(1)
    expect(w.findAll('.icon-fail').length).toBe(1)
    await w.find('.alert-close').trigger('click')
    expect(w.emitted('dismiss')).toHaveLength(1)
  })

  it('все согласованы: success, счётчик ошибок скрыт, без причины отказа', () => {
    const w = mount(BulkApproveReport, {
      props: {
        approved: 2,
        failed: 0,
        rows: [{ uuid: 'a', label: 'УП-1', sub: 'ООО Ромашка', ok: true, message: 'Согласовано' }],
      },
      global: { plugins: [i18n] },
    })
    expect(w.find('.n-alert').attributes('data-type')).toBe('success')
    expect(w.text()).not.toContain('bulkReport.failed')
    expect(w.findAll('.icon-ok').length).toBe(1)
    expect(w.findAll('.icon-fail').length).toBe(0)
  })
})
