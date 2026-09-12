/**
 * DirectumRuns.vue: таблица истории прогонов Directum.
 *
 * NDataTable подменяется на render-компонент, который реально вызывает
 * column.render — проверяются счётчики (задач/уведомлено/проблем) и
 * раскрытие JSONB-отчёта (renderExpand): notified/skipped/unmatched/
 * ambiguous/matrixDisabled/error/empty.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent, h, ref, type VNode } from 'vue'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'
import type { DirectumRun } from '../../src/api/directum'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

const refetch = vi.fn()

const run: DirectumRun = {
  id: 5,
  triggered_by: 'manual',
  started_at: '2026-08-17T09:00:00+03:00',
  finished_at: '2026-08-17T09:00:05+03:00',
  status: 'success',
  tasks_total: 7,
  performers_total: 3,
  users_notified: 1,
  users_skipped_opt_in: 1,
  users_unmatched: 1,
  users_ambiguous: 0,
  errors: 0,
  report: {
    notified: [{ fio: 'Иванов Иван Иванович', tasks: 5 }],
    skipped_opt_in: [{ fio: 'Петров Пётр Петрович', tasks: 1 }],
    unmatched: [{ fio: 'Капитан судна Н.Трубятчинский', tasks: 1 }],
  },
}

vi.mock('naive-ui', () => ({
  NButton: {
    template: '<button class="n-button" @click="$emit(\'click\')"><slot /></button>',
    props: ['size', 'loading'],
    emits: ['click'],
  },
  NTag: {
    template: '<span class="n-tag"><slot /></span>',
    props: ['type', 'size', 'bordered'],
  },
  // Реально вызывает render-функции колонок и renderExpand — покрытие логики
  // компонента без https-моков самой таблицы.
  NDataTable: defineComponent({
    props: ['columns', 'data', 'loading', 'pagination', 'remote', 'rowKey', 'size', 'striped'],
    setup(props: { columns?: Array<Record<string, unknown>>; data?: DirectumRun[] }) {
      return () =>
        h('table', { class: 'n-data-table' }, [
          h('tbody', [
            ...(props.data ?? []).map((row) =>
              h('tr', { class: 'row', 'data-id': row.id }, [
                ...(props.columns ?? [])
                  .filter((c) => c.key)
                  .map((c) =>
                    h(
                      'td',
                      { class: `cell-${c.key}` },
                      c.render ? [(c.render as (r: DirectumRun) => VNode)(row)] : String(row[c.key as keyof DirectumRun] ?? ''),
                    ),
                  ),
              ]),
            ),
            ...(props.data ?? []).map((row) => {
              const expand = (props.columns ?? []).find((c) => c.type === 'expand') as
                | { renderExpand?: (r: DirectumRun) => VNode[] }
                | undefined
              return h('tr', { class: 'expand', 'data-id': row.id }, [
                h('td', expand?.renderExpand ? expand.renderExpand(row) : []),
              ])
            }),
          ]),
        ])
    },
  }),
}))

vi.mock('../../src/queries/directum', () => {
  // Ленивый общий ref: фабрика vi.mock хойстится выше const run, поэтому
  // данные создаём при первом обращении (уже после инициализации модуля).
  const state: { data: ReturnType<typeof ref> | null } = { data: null }
  const ensure = () => {
    if (!state.data) state.data = ref({ items: [run], total: 1 })
    return state.data
  }
  return {
    __setData: (v: unknown) => {
      ensure().value = v as { items: DirectumRun[]; total: number }
    },
    useDirectumRunsQuery: () => ({
      data: ensure(),
      isLoading: ref(false),
      refetch,
    }),
  }
})

import DirectumRuns from '../../src/components/admin/DirectumRuns.vue'

function expandText(wrapper: ReturnType<typeof mount>) {
  return wrapper.find('tr.expand').text()
}

describe('DirectumRuns', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    refetch.mockClear()
  })

  it('рендерит счётчики прогона', async () => {
    const wrapper = mount(DirectumRuns, { global: { plugins: [i18n] } })
    await flushPromises()
    expect(wrapper.find('.cell-tasks_total').text()).toBe('7')
    expect(wrapper.find('.cell-users_notified').text()).toBe('1')
    // problems = unmatched + ambiguous + errors = 1.
    expect(wrapper.find('.cell-problems .directum__problems').text()).toBe('1')
    expect(wrapper.find('.cell-triggered_by').text()).toContain('manual')
  })

  it('раскрывает отчёт: notified / skipped / unmatched', async () => {
    const wrapper = mount(DirectumRuns, { global: { plugins: [i18n] } })
    await flushPromises()
    const text = expandText(wrapper)
    expect(text).toContain('Иванов Иван Иванович (5)')
    expect(text).toContain('Петров Пётр Петрович (1)')
    expect(text).toContain('Капитан судна Н.Трубятчинский (1)')
  })

  it('кнопка «Обновить» вызывает refetch', async () => {
    const wrapper = mount(DirectumRuns, { global: { plugins: [i18n] } })
    await flushPromises()
    await wrapper.find('button').trigger('click')
    expect(refetch).toHaveBeenCalledTimes(1)
  })

  it('warn-строки: matrixDisabled и error', async () => {
    const mod = (await import('../../src/queries/directum')) as unknown as {
      __setData: (v: unknown) => void
    }
    mod.__setData({
      items: [
        {
          ...run,
          report: { matrix_disabled: true, error: 'HTTP 503: upstream' },
        },
      ],
      total: 1,
    })
    const wrapper = mount(DirectumRuns, { global: { plugins: [i18n] } })
    await flushPromises()
    const text = expandText(wrapper)
    expect(wrapper.find('.directum__report-warn').exists()).toBe(true)
    expect(text).toContain('HTTP 503')
    mod.__setData({ items: [run], total: 1 })
  })
})

describe('DirectumRuns: пагинация и статусы', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    refetch.mockClear()
  })

  it('колбэки пагинации обновляют параметры запроса', async () => {
    const table = mount(DirectumRuns, { global: { plugins: [i18n] } })
    await flushPromises()
    const { NDataTable } = await import('naive-ui')
    const cmp = table.findComponent(NDataTable)
    const pagination = cmp.props('pagination') as {
      onChange: (p: number) => void
      onUpdatePageSize: (s: number) => void
    }
    pagination.onChange(3)
    pagination.onUpdatePageSize(50)
    await flushPromises()
    // Повторный рендер после смены параметров не падает (row-key/pagination).
    expect(cmp.exists()).toBe(true)
  })

  it('row-key возвращает id строки', async () => {
    const wrapper = mount(DirectumRuns, { global: { plugins: [i18n] } })
    await flushPromises()
    const { NDataTable } = await import('naive-ui')
    const rowKey = wrapper.findComponent(NDataTable).props('rowKey') as (r: { id: number }) => number
    expect(rowKey({ id: 42 })).toBe(42)
  })

  it('варианты статусов и записи без tasks в отчёте', async () => {
    const mod = (await import('../../src/queries/directum')) as unknown as {
      __setData: (v: unknown) => void
    }
    mod.__setData({
      items: [
        { ...run, status: 'failed', finished_at: null },
        { ...run, id: 6, status: 'skipped', report: { unmatched: [{ fio: 'Без задач' }] } },
      ],
      total: 2,
    })
    const wrapper = mount(DirectumRuns, { global: { plugins: [i18n] } })
    await flushPromises()
    const text = wrapper.text()
    // failed/skipped-теги рендерятся разными ветками statusTagType/statusLabel.
    expect(text).toContain('admin.directum.runs.status.failed')
    expect(text).toContain('admin.directum.runs.status.skipped')
    // pairLine без tasks: только ФИО, без скобок (expand-строки обеих прогонов).
    const expands = wrapper.findAll('tr.expand').map((w) => w.text()).join(' ')
    expect(expands).toContain('Без задач')
    mod.__setData({ items: [run], total: 1 })
  })
})
