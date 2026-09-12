/**
 * Единая точка входа `test` для e2e-спек (аудит тестирования 2026-08-23, P2;
 * review-2 P1.2 — слушатели на ВСЕХ страницах, включая создаваемые вручную;
 * review-3 P1 — точечный allowlist, internal-origin из baseURL, полный
 * teardown слушателей).
 *
 * Playwright не эмитит событие создания контекста на browser (только
 * 'disconnected'), поэтому перехват — обёртка над browser.newContext: она
 * подключает активный коллектор ко всем контекстам, созданным ВО ВРЕМЯ теста
 * (newAdminPage(), публичные/ACL-страницы, browser.newContext(...) в спеках).
 * Уже существующие на старте теста контексты (beforeAll serial-спек)
 * подключаются напрямую; ВСЕ слушатели снимаются в teardown — между
 * serial-тестами ничего не накапливается.
 *
 * Тест падает при:
 *   - pageerror — необработанных исключениях любой страницы;
 *   - console.error — по правилам _isAllowedNetworkError: сетевые ошибки
 *     НЕ-API ресурсов (JS-чанки/CSS/шрифты, любые статусы включая 5xx) —
 *     всегда проблема; 4xx у /api/ и перечисленные внешние сервисы — allow.
 *
 * Легитимные исключения добавлять в CONSOLE_ALLOWLIST /
 * EXTERNAL_ORIGIN_ALLOWLIST с комментарием.
 */
import {
  test as base,
  type Browser,
  type BrowserContext,
  type ConsoleMessage,
  type Page,
} from '@playwright/test'

// Реэкспорт всего остального API (@playwright/test): спеки продолжают
// импортировать Page/Browser/типы из того же './lib/test'.
export * from '@playwright/test'

// Точечные текстовые исключения (сетевыми статусами управляет
// _isAllowedNetworkError). Каждое — с обоснованием.
const CONSOLE_ALLOWLIST: RegExp[] = [
  // Погодный виджет — production-фича; в e2e-контуре нет внешней сети,
  // fetch уходит в CORS-отказ. Не дефект приложения.
  /^Access to fetch at 'https:\/\/api\.open-meteo\.com/,
]

// Внешние origin, чья недоступность в e2e-контуре штатна (нет интернета
// by design). НЕ расширять без обоснования: прочий упавший внешний ресурс
// (CDN/шрифт/скрипт) — проблема теста или приложения (review-3).
const EXTERNAL_ORIGIN_ALLOWLIST: RegExp[] = [/^https:\/\/api\.open-meteo\.com\//]

const API_4XX = /^Failed to load resource: the server responded with a status of 4\d\d /

function _isAllowedNetworkError(text: string, resourceUrl: string | undefined): boolean {
  // «Failed to load resource» — браузерная сетевая диагностика (не JS-ошибка).
  // Правила (review-3, P1):
  //  1) 4xx у /api/ — allow: негативные кейсы спек легитимно генерируют
  //     401/403/404/410/422/429; дефекты API ловятся ассертами спек и
  //     backend-тестами. 5xx у /api/ — НЕ allow: серверная ошибка (в т.ч.
  //     на bootstrap) не должна прятаться за гейтом.
  //  2) внутренние НЕ-API ресурсы (JS-chunk/CSS/шрифты) — любой статус и
  //     сетевые сбои остаются проблемой (review-2: сломанный chunk не
  //     прячется за allowlist).
  //  3) внешний allowlist (open-meteo) — нет внешней сети by design; прочие
  //     внешние origin — проблема (review-3: прежний «любой внешний» на
  //     staging прятал бы и собственные ресурсы за не-localhost origin).
  // internalOrigin вычисляется из baseURL проекта, а не хардкодом.
  if (!/^Failed to load resource/.test(text)) return false
  if (resourceUrl === undefined) return false
  if (API_4XX.test(text) && /\/api\//.test(resourceUrl)) return true
  if (EXTERNAL_ORIGIN_ALLOWLIST.some((pattern) => pattern.test(resourceUrl))) return true
  return false
}

export interface ErrorCollector {
  /** Список накопленных проблем (pageerror/console.error). */
  readonly problems: string[]
  /** Подключить контекст и все его страницы (страницы будущего — тоже). */
  hookContext(context: BrowserContext): void
  /** Снять все слушатели (teardown фикстуры). */
  dispose(): void
  /** Стереть накопленные проблемы (только для мета-спеки gate.spec.ts). */
  clear(): void
}

function _createCollector(browser: Browser): ErrorCollector {
  const problems: string[] = []
  const detachers: Array<() => void> = []
  const attachedPages = new WeakSet<Page>()
  const hookedContexts = new WeakSet<BrowserContext>()

  const attach = (page: Page): void => {
    if (attachedPages.has(page)) return
    attachedPages.add(page)
    const onPageError = (error: Error): void => {
      problems.push(`pageerror: ${error.message}`)
    }
    const onConsole = (message: ConsoleMessage): void => {
      if (message.type() !== 'error') return
      const text = message.text()
      if (CONSOLE_ALLOWLIST.some((pattern) => pattern.test(text))) return
      if (_isAllowedNetworkError(text, message.location()?.url)) return
      problems.push(`console.error: ${text}`)
    }
    page.on('pageerror', onPageError)
    page.on('console', onConsole)
    detachers.push(() => {
      page.off('pageerror', onPageError)
      page.off('console', onConsole)
    })
  }

  const hookContext = (context: BrowserContext): void => {
    if (hookedContexts.has(context)) return
    hookedContexts.add(context)
    const onPage = (page: Page): void => attach(page)
    context.on('page', onPage)
    for (const page of context.pages()) attach(page)
    detachers.push(() => context.off('page', onPage))
  }

  // NB: у Playwright Browser НЕТ события 'context' — новые контексты ловит
  // только патч newContext (см. patchNewContext); здесь хукаем существующие.
  for (const context of browser.contexts()) hookContext(context)

  const collector: ErrorCollector = {
    problems,
    hookContext,
    dispose(): void {
      for (const detach of detachers.splice(0)) detach()
      if (activeCollector === collector) activeCollector = null
    },
    clear(): void {
      problems.length = 0
    },
  }
  return collector
}

// Активный коллектор текущего теста (воркер-процесс исполняет тесты
// последовательно) + одноразовый патч newContext на browser-инстансе.
let activeCollector: ErrorCollector | null = null
const patchedBrowsers = new WeakSet<Browser>()

function patchNewContext(browser: Browser): void {
  if (patchedBrowsers.has(browser)) return
  patchedBrowsers.add(browser)
  const original = browser.newContext.bind(browser)
  browser.newContext = async (...args: Parameters<Browser['newContext']>) => {
    const context = await original(...args)
    const collector = activeCollector
    if (collector !== null) collector.hookContext(context)
    return context
  }
}

/** Коллектор активной авто-фикстуры consoleGate (для мета-спеки). */
export function getActiveCollector(): ErrorCollector | null {
  return activeCollector
}

/**
 * Сбор ошибок всех страниц для мета-спеки (gate.spec.ts): те же правила,
 * что у авто-фикстуры. baseOrigin — как в фикстуре (internal-origin).
 */


export const test = base.extend<{ consoleGate: void }>({
  consoleGate: [
    async ({ browser }, use) => {
      patchNewContext(browser)
      const collector = _createCollector(browser)
      activeCollector = collector

      await use()

      try {
        if (collector.problems.length > 0) {
          throw new Error(
            `Ошибки страницы, не пойманные приложением (аудит 2026-08-23):\n  ${collector.problems
              .slice(0, 10)
              .join('\n  ')}${
              collector.problems.length > 10
                ? `\n  … ещё ${collector.problems.length - 10}`
                : ''
            }`,
          )
        }
      } finally {
        collector.dispose()
      }
    },
    { auto: true },
  ],
})
