import { describe, it, expect } from 'vitest'

/**
 * Тесты конфигурации i18n (src/i18n/index.ts).
 *
 * Парность ключей ru↔en уже проверяется отдельным CI-скриптом
 * `npm run i18n:check` (scripts/check-i18n.js) — здесь только инварианты
 * конфигурации: legacy-режим, дефолтная локаль, fallback, наличие обоих
 * message-объектов, no-op loadLocale.
 */
import { i18n, loadLocale, type AppLocale } from '../../src/i18n'

describe('i18n configuration', () => {
  it('использует Composition API (mode: composition)', () => {
    // createI18n({ legacy: false }) → mode === 'composition' (не legacy).
    // Свойства global доступны через .value (Composition API ref'ы).
    expect(i18n.mode).toBe('composition')
  })

  it('дефолтная локаль — ru', () => {
    expect(i18n.global.locale.value).toBe('ru')
  })

  it('fallback локаль — ru', () => {
    expect(i18n.global.fallbackLocale.value).toBe('ru')
  })

  it('оба message-объекта (ru + en) загружены статически', () => {
    const messages = i18n.global.messages
    expect(messages.value.ru).toBeDefined()
    expect(messages.value.en).toBeDefined()
    expect(Object.keys(messages.value.ru).length).toBeGreaterThan(0)
    expect(Object.keys(messages.value.en).length).toBeGreaterThan(0)
  })

  it('loadLocale — no-op (обе локали бандлятся статически)', async () => {
    // Функция не должна бросать и не должна ничего менять — оба словаря уже загружены.
    await expect(loadLocale('en' as AppLocale)).resolves.toBeUndefined()
    await expect(loadLocale('ru' as AppLocale)).resolves.toBeUndefined()
  })

  it('ru и en имеют общий верхнеуровневый набор доменов', () => {
    const ruDomains = Object.keys(i18n.global.messages.value.ru).sort()
    const enDomains = Object.keys(i18n.global.messages.value.en).sort()
    expect(ruDomains).toEqual(enDomains)
  })
})
