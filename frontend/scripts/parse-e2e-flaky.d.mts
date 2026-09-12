/**
 * Парсер flaky-тестов из Playwright JUnit. Флак-признаки (реальный формат):
 * <flakyError> (thrown/timeout) и <flakyFailure> (упавший expect).
 * CLI: node scripts/parse-e2e-flaky.mjs <xml> [--budget N].
 */
export function validateJunit(xml: string): boolean
/** Throws when XML is malformed or its root is not testsuite/testsuites. */
export function parseFlaky(xml: string): string[]
