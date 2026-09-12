/**
 * Мета-спека для console/pageerror-гейта (review-2, P1.2).
 *
 * Ревью-контрпример: страница, созданная вручную через browser.newContext()
 * (публичные фото, ACL-страницы, newAdminPage), выбрасывает pageerror —
 * прежний гейт слушал только дефолтную страницу и оставался зелёным.
 * Спека доказывает: ошибки ручных контекстов попадают в АКТИВНЫЙ коллектор
 * фикстуры consoleGate — тот самый, который роняет тест.
 *
 * После проверки намеренно сгенерированные ошибки стираются (clear), чтобы
 * авто-фикстура не провалила саму мета-спеку.
 */
import { expect, getActiveCollector, test } from './lib/test'

test.describe('e2e error-gate coverage', () => {
  test('pageerror в ручном context/page ловится гейтом', async ({ browser }) => {
    const collector = getActiveCollector()
    expect(collector, 'активный коллектор фикстуры').not.toBeNull()

    // тот же путь, что newAdminPage()/публичные страницы в спеках
    const context = await browser.newContext()
    const page = await context.newPage()
    // pageerror требует документа — уходим с about:blank
    await page.goto('data:text/html,<html></html>')

    const before = collector!.problems.length
    await page.evaluate(() => {
      setTimeout(() => {
        throw new Error('gate-selfcheck-pageerror')
      }, 0)
    })
    await page.waitForTimeout(300)

    expect(
      collector!.problems.slice(before).join('\n'),
      'pageerror из вручную созданного context/page обязан попадать в гейт',
    ).toContain('gate-selfcheck-pageerror')

    await context.close()
    collector!.clear()
  })

  test('console.error вне allowlist ловится гейтом', async ({ browser }) => {
    const collector = getActiveCollector()
    expect(collector, 'активный коллектор фикстуры').not.toBeNull()

    const context = await browser.newContext()
    const page = await context.newPage()
    await page.goto('data:text/html,<html><body>gate</body></html>')

    const before = collector!.problems.length
    // прямой console.error — не сетевая диагностика, allowlist не применяется
    await page.evaluate(() => {
      console.error('gate-selfcheck-console-error')
    })
    await page.waitForTimeout(150)

    expect(
      collector!.problems.slice(before).join('\n'),
      'console.error из ручного context/page обязан попадать в гейт',
    ).toContain('gate-selfcheck-console-error')

    await context.close()
    collector!.clear()
  })
})
