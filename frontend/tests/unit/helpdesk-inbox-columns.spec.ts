/**
 * Unit-тесты настраиваемых столбцов агентского инбокса helpdesk.
 *
 * ``useHelpdeskInboxColumns`` — единый источник истины для порядка/видимости/
 * ширины колонок с персистенцией в ``localStorage``. Покрываем: дефолтный
 * порядок, операции (reorder/toggle/reset/width), персистенцию, forward-compat
 * (неизвестные/недостающие id, повреждённый JSON), защиту FIXED-колонки subject,
 * и пресет ``'user'`` (фиксированный, без мутаций).
 *
 * Поскольку state модуля создаётся один раз при импорте (реактивный singleton
 * для всего приложения), динамический импорт в beforeEach + vi.resetModules()
 * пересоздаёт модуль с чистым localStorage для каждого теста.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const STORAGE_KEY = 'helpdesk.inbox.columns'

async function loadModule() {
  // Сброс кеша модулей → composable переинициализируется, перечитав localStorage.
  vi.resetModules()
  return (await import('../../src/composables/useHelpdeskInboxColumns')) as typeof import(
    '../../src/composables/useHelpdeskInboxColumns'
  )
}

function setStored(value: unknown) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(value))
}

describe('useHelpdeskInboxColumns — пресет agent', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('дефолтный порядок: number/status/subject/requester/assignee/age/updated', async () => {
    const mod = await loadModule()
    const { visibleColumns } = mod.useHelpdeskInboxColumns('agent')
    expect(visibleColumns.value.map((c) => c.id)).toEqual([
      'number',
      'status',
      'subject',
      'requester',
      'assignee',
      'age',
      'updated',
    ])
  })

  it('subject = FIXED: не попадает в togglableColumns', async () => {
    const mod = await loadModule()
    const { togglableColumns } = mod.useHelpdeskInboxColumns('agent')
    const ids = togglableColumns.value.map((c) => c.id)
    expect(ids).not.toContain('subject')
    // number — hideable:false (идентификатор тикета), тоже не тогглится
    expect(ids).not.toContain('number')
  })

  it('toggleColumn прячет и возвращает колонку', async () => {
    const mod = await loadModule()
    const { state, visibleColumns, toggleColumn } = mod.useHelpdeskInboxColumns('agent')
    toggleColumn('age')
    expect(state.hidden).toContain('age')
    expect(visibleColumns.value.map((c) => c.id)).not.toContain('age')
    toggleColumn('age')
    expect(state.hidden).not.toContain('age')
    expect(visibleColumns.value.map((c) => c.id)).toContain('age')
  })

  it('toggleColumn игнорирует FIXED (subject) и hideable:false (number)', async () => {
    const mod = await loadModule()
    const { state, toggleColumn } = mod.useHelpdeskInboxColumns('agent')
    toggleColumn('subject')
    toggleColumn('number')
    expect(state.hidden).toHaveLength(0)
  })

  it('reorderColumn(movedId, beforeId) переставляет колонку', async () => {
    const mod = await loadModule()
    const { state, reorderColumn } = mod.useHelpdeskInboxColumns('agent')
    // Поставить status перед requester
    reorderColumn('status', 'requester')
    const order = state.order
    expect(order.indexOf('status')).toBeLessThan(order.indexOf('requester'))
    expect(order.indexOf('status')).toBeGreaterThan(order.indexOf('number'))
  })

  it('reorderColumn с beforeId=null двигает в конец', async () => {
    const mod = await loadModule()
    const { state, reorderColumn } = mod.useHelpdeskInboxColumns('agent')
    reorderColumn('number', null)
    expect(state.order[state.order.length - 1]).toBe('number')
  })

  it('reorderColumn отказывается двигать FIXED (subject)', async () => {
    const mod = await loadModule()
    const { state, reorderColumn } = mod.useHelpdeskInboxColumns('agent')
    const before = [...state.order]
    reorderColumn('subject', 'updated')
    expect(state.order).toEqual(before) // без изменений
  })

  it('resetColumns восстанавливает дефолтный порядок и видимость', async () => {
    const mod = await loadModule()
    const { state, toggleColumn, reorderColumn, resetColumns } = mod.useHelpdeskInboxColumns('agent')
    toggleColumn('age')
    reorderColumn('number', null)
    resetColumns()
    expect(state.hidden).toEqual([])
    expect(state.order.indexOf('number')).toBe(0)
  })

  it('setColumnWidth сохраняет и кэмпит ширину', async () => {
    const mod = await loadModule()
    const { state, gridTemplate, setColumnWidth } = mod.useHelpdeskInboxColumns('agent')
    setColumnWidth('requester', 220)
    expect(state.widths.requester).toBe(220)
    expect(gridTemplate.value).toContain('220px')
  })

  it('setColumnWidth кэмпит в диапазоне [48, 600]', async () => {
    const mod = await loadModule()
    const { state, setColumnWidth } = mod.useHelpdeskInboxColumns('agent')
    setColumnWidth('requester', 5)
    expect(state.widths.requester).toBe(48)
    setColumnWidth('requester', 9999)
    expect(state.widths.requester).toBe(600)
  })

  it('setColumnWidth игнорирует FIXED (subject)', async () => {
    const mod = await loadModule()
    const { gridTemplate, setColumnWidth } = mod.useHelpdeskInboxColumns('agent')
    setColumnWidth('subject', 500)
    // subject всегда minmax(0,1fr)
    expect(gridTemplate.value).toContain('minmax(0, 1fr)')
    expect(gridTemplate.value).not.toContain('500px')
  })
})

describe('useHelpdeskInboxColumns — персистенция (localStorage)', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('операции персистятся в localStorage', async () => {
    const mod = await loadModule()
    const { toggleColumn } = mod.useHelpdeskInboxColumns('agent')
    toggleColumn('age')
    const raw = localStorage.getItem(STORAGE_KEY)
    expect(raw).toBeTruthy()
    expect(JSON.parse(raw as string).hidden).toContain('age')
  })

  it('state восстанавливается из storage при повторной инициализации', async () => {
    setStored({ order: ['number', 'status', 'subject', 'age', 'requester', 'assignee', 'updated'], hidden: ['assignee'], widths: { requester: 200 } })
    const mod = await loadModule()
    const { state, visibleColumns } = mod.useHelpdeskInboxColumns('agent')
    expect(state.order).toContain('age')
    expect(state.hidden).toContain('assignee')
    expect(state.widths.requester).toBe(200)
    expect(visibleColumns.value.map((c) => c.id)).not.toContain('assignee')
  })

  it('повреждённый JSON → fallback к дефолту', async () => {
    localStorage.setItem(STORAGE_KEY, '{not valid json')
    const mod = await loadModule()
    const { state, visibleColumns } = mod.useHelpdeskInboxColumns('agent')
    expect(state.order[0]).toBe('number')
    expect(visibleColumns.value.map((c) => c.id)).toEqual([
      'number',
      'status',
      'subject',
      'requester',
      'assignee',
      'age',
      'updated',
    ])
  })

  it('неизвестные id в storage игнорируются (forward-compat)', async () => {
    setStored({ order: ['number', 'status', 'subject', 'future_col', 'requester'], hidden: ['gone_id'] })
    const mod = await loadModule()
    const { state } = mod.useHelpdeskInboxColumns('agent')
    expect(state.order).not.toContain('future_col')
    expect(state.hidden).not.toContain('gone_id')
  })

  it('недостающие дефолтные id дополняются в конец (forward-compat)', async () => {
    // Старая версия без колонки age
    setStored({ order: ['number', 'status', 'subject', 'requester', 'assignee', 'updated'] })
    const mod = await loadModule()
    const { state } = mod.useHelpdeskInboxColumns('agent')
    // age должна появиться (в конце или на дефолтной позиции — главное присутствует)
    expect(state.order).toContain('age')
    // все дефолтные колонки присутствуют
    for (const id of ['number', 'status', 'subject', 'requester', 'assignee', 'age', 'updated']) {
      expect(state.order).toContain(id)
    }
  })

  it('subject нельзя скрыть через storage (защита)', async () => {
    setStored({ order: ['number', 'status', 'subject'], hidden: ['subject'] })
    const mod = await loadModule()
    const { state, visibleColumns } = mod.useHelpdeskInboxColumns('agent')
    expect(state.hidden).not.toContain('subject')
    expect(visibleColumns.value.map((c) => c.id)).toContain('subject')
  })

  it('subject нельзя убрать из порядка через storage', async () => {
    setStored({ order: ['number', 'status', 'requester', 'assignee', 'age', 'updated'] })
    const mod = await loadModule()
    const { state } = mod.useHelpdeskInboxColumns('agent')
    expect(state.order).toContain('subject')
  })

  it('hidden: null в storage → пустой список скрытых', async () => {
    setStored({ hidden: null })
    const mod = await loadModule()
    const { state } = mod.useHelpdeskInboxColumns('agent')
    expect(state.hidden).toEqual([])
  })

  it('некорректная ширина в storage → дефолт/кэмп', async () => {
    setStored({ widths: { requester: 'wide', assignee: -10, age: 99999 } })
    const mod = await loadModule()
    const { state } = mod.useHelpdeskInboxColumns('agent')
    // 'wide' — не число → дефолт
    expect(state.widths.requester).toBe(200)
    // -10 — валидное число, но < MIN → кэмп к MIN_COLUMN_WIDTH (48)
    expect(state.widths.assignee).toBe(48)
    // 99999 — валидное число, но > MAX → кэмп к MAX_COLUMN_WIDTH (600)
    expect(state.widths.age).toBe(600)
  })
})

describe('useHelpdeskInboxColumns — пресет user (фиксированный)', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('порядок: number/status/subject/assignee/updated (без requester/age)', async () => {
    const mod = await loadModule()
    const { visibleColumns } = mod.useHelpdeskInboxColumns('user')
    expect(visibleColumns.value.map((c) => c.id)).toEqual([
      'number',
      'status',
      'subject',
      'assignee',
      'updated',
    ])
  })

  it('mutation-операции — no-op (не персистится)', async () => {
    const mod = await loadModule()
    const { state, toggleColumn, reorderColumn, setColumnWidth } = mod.useHelpdeskInboxColumns('user')
    const orderBefore = [...state.order]
    toggleColumn('assignee')
    reorderColumn('number', null)
    setColumnWidth('assignee', 500)
    expect(state.order).toEqual(orderBefore)
    expect(state.hidden).toEqual([])
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull()
  })
})

describe('useHelpdeskInboxColumns — gridTemplate', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('subject → minmax(0, 1fr), остальные → px', async () => {
    const mod = await loadModule()
    const { gridTemplate } = mod.useHelpdeskInboxColumns('agent')
    // ``minmax(0, 1fr)`` содержит пробел → нельзя просто split(' '). Проверяем
    // наличие нужных фрагментов в строке целиком.
    expect(gridTemplate.value).toContain('56px')
    expect(gridTemplate.value).toContain('92px')
    expect(gridTemplate.value).toContain('minmax(0, 1fr)')
    expect(gridTemplate.value).toContain('200px')
    expect(gridTemplate.value).toContain('80px')
    expect(gridTemplate.value).toContain('104px')
  })

  it('скрытая колонка исчезает из gridTemplate', async () => {
    const mod = await loadModule()
    const { gridTemplate, toggleColumn } = mod.useHelpdeskInboxColumns('agent')
    toggleColumn('age')
    expect(gridTemplate.value).not.toMatch(/\b80px\b/)
    // subject (flex) остаётся
    expect(gridTemplate.value).toContain('minmax(0, 1fr)')
  })
})
