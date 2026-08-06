/**
 * Расчёт «возраста» заявки — сколько полных дней прошло с момента её создания.
 *
 * Бэкенд уже отдаёт ``created_at`` в ``TicketListItemOut`` (строка ISO), поэтому
 * отдельная колонка «Возраст» в инбоксе агента считается на фронте без правок
 * API. Функция вынесена из компонента в утилиту для прямого unit-тестирования
 * (по конвенции проекта — характеристика перед декомпозицией).
 *
 * Граница дня — календарные сутки UTC (``Date.getUTCDate``), не локальные. Для
 * корпоративного интранет-портала в едином часовом поясе разница между UTC и
 * локальной полуночью несущественна, а UTC-расчёт детерминирован в тестах
 * (не зависит от TZ машины CI). Возвращает целое ``>= 0``.
 */
export function ticketAgeDays(createdAt: string, now: Date = new Date()): number {
  const created = new Date(createdAt).getTime()
  if (Number.isNaN(created)) return 0
  const diffMs = now.getTime() - created
  if (diffMs <= 0) return 0
  return Math.floor(diffMs / 86_400_000)
}
