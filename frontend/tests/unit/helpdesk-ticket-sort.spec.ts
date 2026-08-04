/**
 * Unit-тесты состояния серверной сортировки списка заявок.
 *
 * ``useHelpdeskTicketSort`` хранит выбранную колонку + направление и отдаёт
 * параметры для API. Цикл клика ``asc → desc → none → asc`` — третий клик
 * сбрасывает в дефолт (как в почтовых клиентах/OTRS). Покрываем: дефолт,
 * цикл переключения, apiParams-маппинг (columnId → backend field), directionFor.
 */
import { describe, it, expect } from 'vitest'
import { useHelpdeskTicketSort, SORT_FIELD_MAP } from '../../src/composables/useHelpdeskTicketSort'

describe('useHelpdeskTicketSort', () => {
  it('дефолт: нет сортировки, apiParams пуст', () => {
    const { sortColumn, sortOrder, apiParams, directionFor } = useHelpdeskTicketSort()
    expect(sortColumn.value).toBeNull()
    expect(apiParams.value).toEqual({})
    expect(directionFor('number')).toBeNull()
  })

  it('первый клик по новой колонке → asc', () => {
    const { toggle, sortColumn, sortOrder, directionFor } = useHelpdeskTicketSort()
    toggle('number')
    expect(sortColumn.value).toBe('number')
    expect(sortOrder.value).toBe('asc')
    expect(directionFor('number')).toBe('asc')
  })

  it('цикл asc → desc → none → asc для одной колонки', () => {
    const { toggle, sortColumn, sortOrder } = useHelpdeskTicketSort()
    toggle('status') // → asc
    expect(sortColumn.value).toBe('status')
    expect(sortOrder.value).toBe('asc')
    toggle('status') // → desc
    expect(sortOrder.value).toBe('desc')
    toggle('status') // → none
    expect(sortColumn.value).toBeNull()
    toggle('status') // → asc снова
    expect(sortColumn.value).toBe('status')
    expect(sortOrder.value).toBe('asc')
  })

  it('клик по другой колонке переключает на неё с asc', () => {
    const { toggle, sortColumn, sortOrder, directionFor } = useHelpdeskTicketSort()
    toggle('number') // asc
    toggle('updated') // новая колонка → asc
    expect(sortColumn.value).toBe('updated')
    expect(sortOrder.value).toBe('asc')
    expect(directionFor('number')).toBeNull()
    expect(directionFor('updated')).toBe('asc')
  })

  it('apiParams маппит columnId → backend sort field', () => {
    const { toggle, apiParams } = useHelpdeskTicketSort()
    toggle('age')
    expect(apiParams.value).toEqual({ sort: 'created_at', order: 'asc' })
  })

  it('SORT_FIELD_MAP: age → created_at, updated → last_activity_at', () => {
    expect(SORT_FIELD_MAP.age).toBe('created_at')
    expect(SORT_FIELD_MAP.updated).toBe('last_activity_at')
    expect(SORT_FIELD_MAP.number).toBe('number')
    expect(SORT_FIELD_MAP.requester).toBe('requester')
    expect(SORT_FIELD_MAP.assignee).toBe('assignee')
  })

  it('initialSort/initialOrder respected', () => {
    const { sortColumn, sortOrder, apiParams } = useHelpdeskTicketSort('updated', 'desc')
    expect(sortColumn.value).toBe('updated')
    expect(sortOrder.value).toBe('desc')
    expect(apiParams.value).toEqual({ sort: 'last_activity_at', order: 'desc' })
  })

  it('после сброса (none) apiParams снова пуст', () => {
    const { toggle, apiParams } = useHelpdeskTicketSort()
    toggle('number') // asc
    toggle('number') // desc
    toggle('number') // none
    expect(apiParams.value).toEqual({})
  })
})
