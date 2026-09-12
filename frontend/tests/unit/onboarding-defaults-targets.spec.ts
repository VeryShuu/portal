/**
 * Тесты данных экскурса: дефолтные шаги (defaultOnboardingSteps) и справочник
 * готовых целей тура (TOUR_TARGETS). Реальный i18n — проверяем фактические
 * тексты ключей onboarding.steps.* и nav.*.
 */
import { describe, it, expect, vi } from 'vitest'

vi.mock('../../src/api', () => ({ api: vi.fn() }))

import { defaultOnboardingSteps } from '../../src/stores/onboarding'
import { TOUR_TARGETS, getTourTargetOptions, tourTargetLabelFor } from '../../src/utils/tourTargets'
import { i18n } from '../../src/i18n'

describe('defaultOnboardingSteps', () => {
  it('содержит шаги всех ключевых разделов в порядке меню', () => {
    const steps = defaultOnboardingSteps()
    expect(steps.map((s) => s.id)).toEqual([
      'default-news',
      'default-kb',
      'default-files',
      'default-links',
      'default-staff',
      'default-meetings',
      'default-photo-gallery',
      'default-helpdesk',
      'default-profile',
    ])
  })

  it('новые разделы помечены is_new для delta-тура уже прошедших пользователей', () => {
    const byId = new Map(defaultOnboardingSteps().map((s) => [s.id, s]))
    expect(byId.get('default-files')?.is_new).toBe(true)
    expect(byId.get('default-staff')?.is_new).toBe(true)
    expect(byId.get('default-meetings')?.is_new).toBe(true)
    expect(byId.get('default-photo-gallery')?.is_new).toBe(true)
    expect(byId.get('default-helpdesk')?.is_new).toBe(true)
    expect(byId.get('default-news')?.is_new).toBe(false)
    expect(byId.get('default-profile')?.is_new).toBe(false)
  })

  it('тексты шагов берутся из i18n и непустые (ru + en)', () => {
    for (const locale of ['ru', 'en'] as const) {
      i18n.global.locale.value = locale
      for (const s of defaultOnboardingSteps()) {
        expect(s.title.trim(), `${locale}: ${s.id}.title`).not.toBe('')
        expect(s.body.trim(), `${locale}: ${s.id}.body`).not.toBe('')
        // Неразрешённый ключ vue-i18n возвращает сам ключ — отлавливаем это
        expect(s.title, `${locale}: ${s.id}.title`).not.toMatch(/^onboarding\./)
      }
    }
    i18n.global.locale.value = 'ru'
  })
})

describe('TOUR_TARGETS', () => {
  it('включает цели новых разделов: техподдержка, инбокс агентов, настройки', () => {
    const selectors = TOUR_TARGETS.map((t) => t.selector)
    expect(selectors).toContain('.n-menu-item:has([data-tour-id="helpdesk-my"])')
    expect(selectors).toContain('.n-menu-item:has([data-tour-id="helpdesk-inbox"])')
    expect(selectors).toContain('.n-menu-item:has([data-tour-id="settings"])')
  })

  it('селекторы уникальны и каждый пункт меню следует единому формату', () => {
    const selectors = TOUR_TARGETS.map((t) => t.selector)
    expect(new Set(selectors).size).toBe(selectors.length)
    for (const t of TOUR_TARGETS) {
      if (t.selector.startsWith('.n-menu-item')) {
        expect(t.selector).toMatch(/^\.n-menu-item:has\(\[data-tour-id="[\w-]+"\]\)$/)
      }
    }
  })

  it('getTourTargetOptions/tourTargetLabelFor разрешают локализованные подписи', () => {
    const options = getTourTargetOptions()
    expect(options).toHaveLength(TOUR_TARGETS.length)
    for (const o of options) {
      expect(o.label.trim()).not.toBe('')
      expect(o.label).not.toMatch(/^(nav|admin|feedback)\./)
      expect(tourTargetLabelFor(o.selector)).toBe(o.label)
    }
    expect(tourTargetLabelFor('.unknown-selector')).toBeNull()
  })
})
