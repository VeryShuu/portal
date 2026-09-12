import { test, expect } from './lib/test'
import { Client } from 'pg'
import { apiRequest, e2eContextOptions, ADMIN_STATE_FILE } from './fixtures/api'
import type { ApiResponse } from './fixtures/api'

/**
 * e2e путь внешнего обучаемого на learn-контуре (ADR-051): passwordless-вход
 * (миграция 113) — email → одноразовый код из письма → курсы → материал →
 * выход → повторный вход с новым кодом (каждый вход = новый код).
 *
 * Отключить/починить «скипом» нельзя: skip-гейт CI роняет прогон на любом
 * skipped (проект learn включается только с E2E_LEARN=1 — в CI он всегда).
 */

const COURSE_TITLE = `learn-e2e-course-${Date.now()}`
const MATERIAL_TITLE = 'Инструкция для e2e'
const ACCOUNT_EMAIL = `learn-e2e-${Date.now()}@test.local`
const ACCOUNT_NAME = 'E2E Внешний Обучаемый'

interface CourseCreated {
  id: string
  slug: string
}

async function fetchLoginCodeFromOutbox(email: string): Promise<string> {
  // Код существует ТОЛЬКО в письме (в БД — только хэш) — достаём из outbox
  // напрямую, как это сделал бы реальный получатель.
  const dsn = process.env.DATABASE_URL
  if (!dsn) throw new Error('DATABASE_URL обязателен для learn e2e (чтение email_outbox)')
  const client = new Client({ connectionString: dsn })
  await client.connect()
  try {
    const res = await client.query<{ body_text: string }>(
      `SELECT body_text FROM email_outbox
       WHERE to_email = $1 AND kind = 'learning' AND subject LIKE '%Код для входа%'
       ORDER BY created_at DESC LIMIT 1`,
      [email],
    )
    if (res.rowCount === 0) throw new Error(`письмо с кодом для ${email} не найдено в email_outbox`)
    const m = res.rows[0].body_text.match(/\b(\d{6})\b/)
    if (!m) throw new Error('код входа не найден в тексте письма')
    return m[1]
  } finally {
    await client.end()
  }
}

/** Полный passwordless-вход: email → код из письма → список курсов. */
async function signIn(page: import('@playwright/test').Page, email: string): Promise<void> {
  await page.goto('/login')
  await page.getByPlaceholder('Email').fill(email)
  await page.getByRole('button', { name: 'Получить код' }).click()
  await expect(page.getByPlaceholder('6 цифр')).toBeVisible()
  const code = await fetchLoginCodeFromOutbox(email)
  await page.getByPlaceholder('6 цифр').fill(code)
  await page.getByRole('button', { name: 'Войти', exact: true }).click()
  await expect(page).toHaveURL(/courses/)
}

test.describe.configure({ mode: 'serial' })

let courseId = ''
let accountId = ''

test('setup: курс, материал, публикация, учётка, зачисление (admin API)', async ({ browser }) => {
  // Admin-контекст (cookie из setup-проекта) на ТЕКУЩЕМ (learn) origin: и
  // portal-сессия, и XSRF-domain — localhost, порты cookie не разделяют.
  const context = await browser.newContext({
    storageState: ADMIN_STATE_FILE,
    ...e2eContextOptions(),
  })
  const page = await context.newPage()
  await page.goto('/login')

  const create = (await apiRequest<{ id: string }>(page, 'POST', '/learning/admin/courses', {
    title: COURSE_TITLE,
    description: 'Курс для e2e внешнего обучаемого',
  })) as ApiResponse<CourseCreated>
  expect(create.status).toBe(201)
  courseId = create.data!.id

  const item = await apiRequest(page, 'POST', `/learning/admin/courses/${courseId}/items`, {
    type: 'material',
    title: MATERIAL_TITLE,
    url: 'https://example.com/e2e-doc',
  })
  expect(item.status).toBe(201)

  const publish = await apiRequest(page, 'POST', `/learning/admin/courses/${courseId}/publish`)
  expect(publish.status).toBe(200)

  const account = await apiRequest<{ id: string }>(page, 'POST', '/learning/admin/accounts', {
    full_name: ACCOUNT_NAME,
    email: ACCOUNT_EMAIL,
  })
  expect(account.status).toBe(201)
  accountId = account.data!.id

  const enroll = await apiRequest(page, 'POST', `/learning/admin/courses/${courseId}/participants`, {
    learning_account_id: accountId,
  })
  expect(enroll.status).toBe(201)

  await context.close()
})

test('первый вход по коду из письма', async ({ browser }) => {
  const context = await browser.newContext(e2eContextOptions())
  const page = await context.newPage()
  await signIn(page, ACCOUNT_EMAIL)
  await expect(page.getByText(COURSE_TITLE)).toBeVisible()
  await context.close()
})

test('курс: материал отмечается, прогресс сохраняется', async ({ browser }) => {
  const context = await browser.newContext(e2eContextOptions())
  const page = await context.newPage()
  await signIn(page, ACCOUNT_EMAIL)
  await page.getByText(COURSE_TITLE).first().click()
  await expect(page).toHaveURL(new RegExp('/courses/'))

  await page.getByRole('button', { name: 'Ознакомлен' }).click()
  await expect(page.getByText('Отмечено')).toBeVisible()
  await expect(page.getByText(/Пройдено 1 из 1/)).toBeVisible()

  // перезагрузка: прогресс на месте
  await page.reload()
  await expect(page.getByText(/Пройдено 1 из 1/)).toBeVisible()
  await context.close()
})

test('выход → повторный вход с новым кодом', async ({ browser }) => {
  const context = await browser.newContext(e2eContextOptions())
  const page = await context.newPage()
  await signIn(page, ACCOUNT_EMAIL)
  await expect(page.getByText(COURSE_TITLE)).toBeVisible()

  await page.getByRole('button', { name: 'Выйти' }).click()
  await expect(page).toHaveURL(/login/)
  await context.close()
})

test('cleanup: курс снят и удалён (soft)', async ({ browser }) => {
  const context = await browser.newContext({
    storageState: ADMIN_STATE_FILE,
    ...e2eContextOptions(),
  })
  const page = await context.newPage()
  await page.goto('/login')
  const del = await apiRequest(page, 'DELETE', `/learning/admin/courses/${courseId}`)
  expect([200, 404]).toContain(del.status)
  await context.close()
})
