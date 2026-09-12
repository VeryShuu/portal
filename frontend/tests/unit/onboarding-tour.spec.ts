/**
 * Тесты плеера экскурса (OnboardingTour.vue):
 * - автозапуск полного тура для пользователя без отметки пройденного;
 * - delta-режим по непросмотренным is_new-шагам;
 * - «Пропустить» засчитывает только реально показанные шаги;
 * - LS-ключи привязаны к пользователю (общий компьютер) + чистка легаси-ключей;
 * - Esc закрывает тур; ручной запуск уважает выключенный модуль
 *   и фильтрует шаги без цели в DOM.
 * Плюс видимость пункта «Пройти экскурс снова» в HeaderUserMenu.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { reactive, nextTick } from 'vue'
import type { VueWrapper } from '@vue/test-utils'

const patchMyPreferences = vi.fn().mockResolvedValue(undefined)

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (k: string, p?: Record<string, unknown>) => (p ? `${k} ${JSON.stringify(p)}` : k),
  }),
}))

let authMock: { user: Record<string, unknown> | null }
vi.mock('../../src/stores/auth', () => ({ useAuthStore: () => authMock }))

let onboardingMock: Record<string, unknown>
vi.mock('../../src/stores/onboarding', () => ({ useOnboardingSettingsStore: () => onboardingMock }))

vi.mock('../../src/api/users', () => ({
  patchMyPreferences: (...args: unknown[]) => patchMyPreferences(...args),
}))

vi.mock('naive-ui', () => ({
  NDropdown: {
    name: 'NDropdown',
    props: ['options', 'placement'],
    emits: ['select'],
    template: '<div class="n-dropdown-stub"><slot /></div>',
  },
  NIcon: { name: 'NIcon', template: '<i><slot /></i>' },
}))

vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))

import OnboardingTour from '../../src/components/OnboardingTour.vue'
import HeaderUserMenu from '../../src/components/layout/HeaderUserMenu.vue'

type TestUser = {
  id: string
  full_name: string
  preferences: Record<string, unknown>
}

function makeUser(id: string, preferences: Record<string, unknown> = {}): TestUser {
  return { id, full_name: 'Test User', preferences }
}

function seedSteps(): void {
  onboardingMock.onboardingSteps = [
    { id: 'a', selector: '#tour-a', title: 'A', body: '', is_new: false },
    { id: 'b', selector: '#tour-b', title: 'B', body: '', is_new: false },
    { id: 'n1', selector: '#tour-n1', title: 'N1', body: '', is_new: true },
    { id: 'n2', selector: '#tour-n2', title: 'N2', body: '', is_new: true },
  ]
}

let wrapper: VueWrapper | null = null

function mountTour(): VueWrapper {
  wrapper = mount(OnboardingTour, { attachTo: document.body })
  return wrapper
}

/** Прокрутить отложенный автозапуск (800 мс) и дать микро-задачам отработать. */
async function runAutoStart(): Promise<void> {
  await vi.advanceTimersByTimeAsync(800)
  await nextTick()
}

async function settle(): Promise<void> {
  await vi.advanceTimersByTimeAsync(0)
  await nextTick()
}

function overlay(): Element | null {
  return document.querySelector('.tour-overlay')
}

describe('OnboardingTour (плеер экскурса)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    document.body.innerHTML =
      '<div id="app-root"></div>' +
      '<div id="tour-a"></div><div id="tour-b"></div>' +
      '<div id="tour-n1"></div><div id="tour-n2"></div>'
    localStorage.clear()
    patchMyPreferences.mockClear()
    authMock = reactive({ user: makeUser('u1') })
    onboardingMock = reactive({
      loaded: true,
      onboardingEnabled: true,
      onboardingResetTrigger: '',
      onboardingSteps: [] as unknown[],
    })
  })

  afterEach(() => {
    wrapper?.unmount()
    wrapper = null
    vi.useRealTimers()
    document.body.innerHTML = ''
  })

  it('автозапускает полный тур для пользователя без отметки пройденного', async () => {
    seedSteps()
    mountTour()
    await runAutoStart()
    expect(overlay()).toBeTruthy()
    expect(document.querySelectorAll('.tour-dot')).toHaveLength(4)
  })

  it('не автозапускается, когда тур пройден и непросмотренных новинок нет', async () => {
    seedSteps()
    authMock.user = makeUser('u1', {
      onboarding_completed: true,
      onboarding_seen_step_ids: ['a', 'b', 'n1', 'n2'],
    })
    mountTour()
    await runAutoStart()
    expect(overlay()).toBeNull()
  })

  it('delta-тур показывает только непросмотренные новинки', async () => {
    seedSteps()
    authMock.user = makeUser('u1', {
      onboarding_completed: true,
      onboarding_seen_step_ids: ['n1'],
    })
    mountTour()
    await runAutoStart()
    expect(overlay()).toBeTruthy()
    expect(document.querySelectorAll('.tour-dot')).toHaveLength(1)
  })

  it('«Пропустить» в delta-туре засчитывает только показанный шаг', async () => {
    seedSteps()
    authMock.user = makeUser('u1', { onboarding_completed: true })
    mountTour()
    await runAutoStart()
    expect(document.querySelectorAll('.tour-dot')).toHaveLength(2)

    ;(document.querySelector('.tour-skip') as HTMLElement).click()
    await settle()

    expect(patchMyPreferences).toHaveBeenCalledTimes(1)
    const patch = patchMyPreferences.mock.calls[0][0] as Record<string, unknown>
    expect(patch.onboarding_completed).toBeUndefined()
    expect(patch.onboarding_seen_step_ids).toEqual(['n1'])
    const user = authMock.user as TestUser
    expect(user.preferences.onboarding_seen_step_ids).toEqual(['n1'])
  })

  it('завершение полного тура помечает пройденное и пишет per-user LS-ключи', async () => {
    seedSteps()
    // Легаси-ключи старого формата (без привязки к пользователю)
    localStorage.setItem('portal-onboarding-done', '1')
    localStorage.setItem('portal-onboarding-reset-trigger', 'x')

    mountTour()
    await runAutoStart()
    expect(overlay()).toBeTruthy()

    for (let i = 0; i < 4; i++) {
      ;(document.querySelector('.tour-btn--primary') as HTMLElement).click()
      await settle()
    }
    expect(overlay()).toBeNull()

    const patch = patchMyPreferences.mock.calls[0][0] as Record<string, unknown>
    expect(patch.onboarding_completed).toBe(true)
    expect(patch.onboarding_completed_via).toBe('finished')
    expect(patch.onboarding_seen_step_ids).toEqual(['a', 'b', 'n1', 'n2'])
    expect(localStorage.getItem('portal-onboarding-done:u1')).toBe('1')
    expect(localStorage.getItem('portal-onboarding-done')).toBeNull()
    expect(localStorage.getItem('portal-onboarding-reset-trigger')).toBeNull()
  })

  it('второй пользователь на том же браузере получает свой тур (общий компьютер)', async () => {
    seedSteps()
    mountTour()
    await runAutoStart()
    for (let i = 0; i < 4; i++) {
      ;(document.querySelector('.tour-btn--primary') as HTMLElement).click()
      await settle()
    }
    expect(localStorage.getItem('portal-onboarding-done:u1')).toBe('1')

    // Смена пользователя на том же браузере: LS первого не должен глушить тур
    authMock.user = makeUser('u2')
    await runAutoStart()
    expect(overlay()).toBeTruthy()
  })

  it('Esc закрывает активный тур', async () => {
    seedSteps()
    mountTour()
    await runAutoStart()
    expect(overlay()).toBeTruthy()

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await settle()

    expect(overlay()).toBeNull()
    expect(patchMyPreferences).toHaveBeenCalledTimes(1)
    const patch = patchMyPreferences.mock.calls[0][0] as Record<string, unknown>
    expect(patch.onboarding_completed_via).toBe('skipped')
  })

  it('«Напомнить позже» закрывает delta-тур без записи просмотров', async () => {
    seedSteps()
    authMock.user = makeUser('u1', { onboarding_completed: true })
    mountTour()
    await runAutoStart()
    expect(document.querySelectorAll('.tour-dot')).toHaveLength(2)

    const laterBtn = document.querySelector('.tour-btn--ghost') as HTMLElement
    expect(laterBtn).toBeTruthy()
    laterBtn.click()
    await settle()

    expect(overlay()).toBeNull()
    expect(patchMyPreferences).not.toHaveBeenCalled()
    // преференсы не тронуты — новинки предложатся снова
    const user = authMock.user as TestUser
    expect(user.preferences.onboarding_seen_step_ids).toBeUndefined()
  })

  it('фокус-трап: Tab циклит фокус внутри карточки', async () => {
    seedSteps()
    mountTour()
    await runAutoStart()
    expect(overlay()).toBeTruthy()

    const primary = document.querySelector('.tour-btn--primary') as HTMLElement
    const skipBtn = document.querySelector('.tour-skip') as HTMLElement
    expect(document.activeElement).toBe(primary)

    // Tab на последней кнопке → перенос на первую (skip)
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab' }))
    await settle()
    expect(document.activeElement).toBe(skipBtn)

    // Shift+Tab на первой → на последнюю
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', shiftKey: true }))
    await settle()
    expect(document.activeElement).toBe(primary)
  })

  it('мобильная раскладка: карточка-шторка у нижнего края (<768px)', async () => {
    seedSteps()
    Object.defineProperty(window, 'innerWidth', { value: 375, configurable: true })
    try {
      mountTour()
      await runAutoStart()
      expect(overlay()).toBeTruthy()
      const popover = document.querySelector('.tour-popover') as HTMLElement
      expect(popover.style.bottom).toBe('16px')
      expect(popover.style.width).toBe('auto')
    } finally {
      Object.defineProperty(window, 'innerWidth', { value: 1024, configurable: true })
    }
  })

  it('цели меню резолвятся без :has() — через data-tour-id + closest', async () => {
    document.body.insertAdjacentHTML(
      'beforeend',
      '<div class="n-menu-item"><span data-tour-id="legacy-x">X</span></div>',
    )
    onboardingMock.onboardingSteps = [
      { id: 'lx', selector: '.n-menu-item:has([data-tour-id="legacy-x"])', title: 'LX', body: '', is_new: false },
    ]
    mountTour()
    await runAutoStart()
    expect(overlay()).toBeTruthy()
    // подсветка навешивается на родительский .n-menu-item, а не на внутренний span
    expect(document.querySelector('.tour-highlight')).toBeTruthy()
  })

  it('прокручивает цель в центр видимости (scrollIntoView)', async () => {
    seedSteps()
    const scrollSpy = vi.fn()
    Element.prototype.scrollIntoView = scrollSpy as unknown as () => void
    try {
      mountTour()
      await runAutoStart()
      expect(overlay()).toBeTruthy()
      expect(scrollSpy).toHaveBeenCalledWith({ block: 'center', inline: 'nearest' })
    } finally {
      Reflect.deleteProperty(Element.prototype, 'scrollIntoView')
    }
  })

  it('ручной запуск не стартует тур при выключенном модуле', async () => {
    seedSteps()
    onboardingMock.onboardingEnabled = false
    const w = mountTour()
    ;(w.vm as unknown as { startTour: () => void }).startTour()
    await settle()
    expect(overlay()).toBeNull()
  })

  it('шаги без цели в DOM пропускаются', async () => {
    onboardingMock.onboardingSteps = [
      { id: 'a', selector: '#tour-a', title: 'A', body: '', is_new: false },
      { id: 'x', selector: '#does-not-exist', title: 'X', body: '', is_new: false },
    ]
    const w = mountTour()
    ;(w.vm as unknown as { startTour: () => void }).startTour()
    await settle()
    expect(overlay()).toBeTruthy()
    expect(document.querySelectorAll('.tour-dot')).toHaveLength(1)
  })
})

describe('HeaderUserMenu (пункт перезапуска экскурса)', () => {
  function mountMenu(): VueWrapper {
    wrapper = mount(HeaderUserMenu, {
      props: { onAbout: vi.fn() },
      global: { stubs: { UserAvatar: true } },
      attachTo: document.body,
    })
    return wrapper
  }

  function optionKeys(w: VueWrapper): string[] {
    const dd = w.findComponent({ name: 'NDropdown' })
    const options = dd.props('options') as Array<{ key?: string }>
    return options.map((o) => String(o.key))
  }

  beforeEach(() => {
    document.body.innerHTML = ''
    localStorage.clear()
    authMock = reactive({ user: makeUser('u1') })
    onboardingMock = reactive({
      loaded: true,
      onboardingEnabled: true,
      onboardingResetTrigger: '',
      onboardingSteps: [],
    })
  })

  afterEach(() => {
    wrapper?.unmount()
    wrapper = null
  })

  it('пункт виден при включённом модуле', () => {
    const w = mountMenu()
    expect(optionKeys(w)).toContain('replay-tour')
  })

  it('пункт скрыт при выключенном модуле', () => {
    onboardingMock.onboardingEnabled = false
    const w = mountMenu()
    expect(optionKeys(w)).not.toContain('replay-tour')
  })

  it('пункт виден, пока настройки модуля не загружены', () => {
    onboardingMock.loaded = false
    onboardingMock.onboardingEnabled = false
    const w = mountMenu()
    expect(optionKeys(w)).toContain('replay-tour')
  })
})
