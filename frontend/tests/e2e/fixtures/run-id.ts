/**
 * Уникальный идентификатор прогона e2e — используется для префиксации
 * имён создаваемых сущностей (пользователи, разделы, статьи, альбомы),
 * чтобы при параллельном/повторном запуске не возникало конфликтов
 * по уникальным ключам.
 */
export const E2E_RUN_ID = `e2e-${Date.now().toString(36)}-${Math.random()
  .toString(36)
  .slice(2, 8)}`

export function runScopedEmail(local: string, domain = 'portal.local'): string {
  return `${E2E_RUN_ID}-${local}@${domain}`
}
