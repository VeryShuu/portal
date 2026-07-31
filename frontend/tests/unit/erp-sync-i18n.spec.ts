import { describe, it, expect } from 'vitest'

/**
 * Защита от регрессии namespace-mismatch (баг 2026-07-31):
 * компоненты ErpSyncSettings/Runs/Tab искали admin.erpSync.*, а переводы лежали
 * под admin.modules.erpSync.* (orphan) → все тексты вкладки как ключи.
 *
 * Тест фиксирует контракт: блок admin.erpSync существует в обеих локалях и
 * содержит все подсекции, на которые ссылаются компоненты, плюс критические
 * листовые ключи. Глубокая проверка каждого листа избыточна — покрываем
 * структурные узлы, которые компоненты адресуют напрямую.
 */
import ru from '../../src/i18n/ru.json'
import en from '../../src/i18n/en.json'

function flatLeaves(obj: unknown, prefix = ''): string[] {
  if (obj && typeof obj === 'object') {
    return Object.entries(obj as Record<string, unknown>).flatMap(([k, v]) =>
      flatLeaves(v, prefix ? `${prefix}.${k}` : k),
    )
  }
  return [prefix]
}

describe('ERP i18n: admin.erpSync.* присутствует в обеих локалях', () => {
  const ruErp = (ru as any).admin?.erpSync
  const enErp = (en as any).admin?.erpSync

  it('блок admin.erpSync существует в ru и en', () => {
    expect(ruErp).toBeTruthy()
    expect(enErp).toBeTruthy()
  })

  it('переводы НЕ остались под admin.modules.erpSync (orphan-блок убран)', () => {
    // admin.modules.erpSync должна быть краткой карточкой {title,hint}, не полным блоком.
    expect((ru as any).admin?.modules?.erpSync?.settings).toBeUndefined()
    expect((en as any).admin?.modules?.erpSync?.settings).toBeUndefined()
    // но сама карточка {title,hint} там остаётся для ModulesTab.
    expect((ru as any).admin?.modules?.erpSync?.title).toBeTruthy()
    expect((en as any).admin?.modules?.erpSync?.title).toBeTruthy()
  })

  it('ключевые подсекции, адресуемые компонентами, есть', () => {
    for (const sub of ['settings', 'actions', 'runs', 'report']) {
      expect(ruErp[sub], `ru.admin.erpSync.${sub}`).toBeTruthy()
      expect(enErp[sub], `en.admin.erpSync.${sub}`).toBeTruthy()
    }
  })

  it('динамические enum-ключи runs.status.* и runs.trigger.* покрыты', () => {
    for (const status of ['success', 'partial', 'failed', 'skipped']) {
      expect(ruErp.runs.status[status], `ru runs.status.${status}`).toBeTruthy()
      expect(enErp.runs.status[status], `en runs.status.${status}`).toBeTruthy()
    }
    for (const trigger of ['cron', 'manual']) {
      expect(ruErp.runs.trigger[trigger], `ru runs.trigger.${trigger}`).toBeTruthy()
      expect(enErp.runs.trigger[trigger], `en runs.trigger.${trigger}`).toBeTruthy()
    }
  })

  it('report.fields.* покрыты (birth_date, gender)', () => {
    for (const f of ['birth_date', 'gender']) {
      expect(ruErp.report.fields[f]).toBeTruthy()
      expect(enErp.report.fields[f]).toBeTruthy()
    }
  })

  it('набор листьев ru и en совпадает (нет пропусков при переводе)', () => {
    const ruLeaves = new Set(flatLeaves(ruErp))
    const enLeaves = new Set(flatLeaves(enErp))
    const onlyRu = [...ruLeaves].filter((k) => !enLeaves.has(k))
    const onlyEn = [...enLeaves].filter((k) => !ruLeaves.has(k))
    expect(onlyRu, 'ключи есть в ru, но нет в en').toEqual([])
    expect(onlyEn, 'ключи есть в en, но нет в ru').toEqual([])
  })
})
