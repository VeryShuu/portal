/**
 * E2E happy path модуля «Согласование документов» (docs/approvals.md §9).
 *
 * Гейт модуля — реальный (PUT /admin/modules/approvals), а вызовы, зависящие
 * от 1С (список/карточка/согласование), изолируются через page.route —
 * в CI-контуре живой 1С нет, а страница должна отработать полный цикл:
 * список → быстрое согласование → карточка-Drawer.
 *
 * Для настройки нужен admin storageState (auth.setup: E2E_ADMIN_EMAIL/PASSWORD).
 */
import { type Browser, type Page, expect } from './lib/test'
import { test } from './lib/test'
import { apiRequest, newAdminPage } from './fixtures/api'

// Документ-фикстура в нормализованном контракте бэкенда (snake_case).
function supplierDoc(guid: string) {
  return {
    guid,
    doc_type: 'ЗаказПоставщику',
    number: 'МГЦБ-007716',
    date: '04.09.2026 11:06:15',
    organization: 'МАГЭ АО',
    manager: 'Валиева Эльвина Ильнуровна',
    comment: '',
    contractor: 'Контрагент договора ГПХ',
    project: 'Проект-1',
    amount: 12500.5,
    currency: 'RUB',
    activity_direction: null,
    requires_manager: false,
    has_prices: true,
    history: [
      {
        period: '04.09.2026 10:00',
        user: 'Валиева Эльвина Ильнуровна',
        event: 'Создан документ',
        comment: '',
        stage: 'Старт',
      },
    ],
    products: [{ name: 'Работы по договору ГПХ', quantity: '1', price: 12500.5, total: 12500.5 }],
    managers: [],
  }
}

test.describe.serial('Согласование документов (approvals)', () => {
  let adminPage: Page

  test.beforeAll(async ({ browser }: { browser: Browser }) => {
    adminPage = await newAdminPage(browser)
    // Реальный гейт: включаем модуль как админ (после теста выключаем).
    const resp = await apiRequest(adminPage, 'PUT', '/admin/modules/approvals', { enabled: true })
    expect(resp.status).toBe(200)
  })

  test.afterAll(async () => {
    if (adminPage) {
      await apiRequest(adminPage, 'PUT', '/admin/modules/approvals', { enabled: false })
    }
  })

  test('пункт меню виден при включённом модуле', async () => {
    await adminPage.goto('/')
    await expect(adminPage.getByText('Согласование', { exact: true }).first()).toBeVisible()
  })

  test('список → быстрое согласование → документ уходит из списка', async () => {
    const docs = [supplierDoc('g-1')]
    await adminPage.route('**/api/v1/approvals', async (route) =>
      route.fulfill({ status: 200, json: { items: docs, total: docs.length } }),
    )
    await adminPage.route('**/api/v1/approvals/g-1/approve', async (route) => {
      docs.length = 0 // после согласования документ покидает очередь
      await route.fulfill({ status: 200, json: { ok: true, message: 'Согласовано' } })
    })
    await adminPage.route('**/api/v1/approvals/g-1/reject', async (route) =>
      route.fulfill({ status: 200, json: { ok: true, message: 'Отклонено' } }),
    )

    await adminPage.goto('/approvals')
    await expect(adminPage.getByText('МГЦБ-007716').first()).toBeVisible()
    await expect(adminPage.getByText('Контрагент договора ГПХ')).toBeVisible()
    await expect(
      adminPage.getByRole('button', { name: 'Согласовать выбранные (0)' }),
    ).toBeDisabled()

    await adminPage.getByRole('button', { name: 'Согласовать', exact: true }).click()
    // Тост с текстом 1С + документ исчез после инвалилации списка.
    await expect(adminPage.getByText('Согласовано', { exact: true })).toBeVisible()
    await expect(adminPage.getByText('МГЦБ-007716')).toBeHidden()
  })

  test('карточка-Drawer: реквизиты, товары, история', async () => {
    const doc = supplierDoc('g-2')
    await adminPage.route('**/api/v1/approvals', async (route) =>
      route.fulfill({ status: 200, json: { items: [doc], total: 1 } }),
    )
    await adminPage.route('**/api/v1/approvals/g-2', async (route) =>
      route.fulfill({
        status: 200,
        json: { ...doc, attachments: [{ index: 0, name: 'Счёт.pdf' }] },
      }),
    )

    await adminPage.goto('/approvals')
    await adminPage.getByRole('button', { name: 'Подробнее' }).click()

    const drawer = adminPage.locator('.apr-detail__props')
    await expect(drawer).toBeVisible()
    await expect(drawer.getByText('МАГЭ АО')).toBeVisible()
    await expect(drawer.getByText('Контрагент договора ГПХ')).toBeVisible()
    await expect(adminPage.getByText('Работы по договору ГПХ')).toBeVisible()
    // История согласования — свёрнута, раскрываем; вложения — сразу видны
    await expect(adminPage.getByText('История согласования')).toBeVisible()
    await adminPage.getByText('История согласования').click()
    await expect(adminPage.getByText('Создан документ')).toBeVisible()
    await expect(adminPage.getByText('Счёт.pdf')).toBeVisible()
    // Отклонение заблокировано без комментария, согласование доступно
    const drawerButtons = adminPage.locator('.apr-detail__buttons')
    await expect(drawerButtons.getByRole('button', { name: 'Отклонить' })).toBeDisabled()
    await expect(
      drawerButtons.getByRole('button', { name: 'Согласовать', exact: true }),
    ).toBeEnabled()
  })
})
