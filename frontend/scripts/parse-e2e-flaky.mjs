/**
 * Парсер flaky-тестов из Playwright JUnit-выхлопа (audit-review follow-up², P1).
 *
 * Формат проверен на РЕАЛЬНОМ выводе Playwright (includeRetries: true):
 *   - флак с thrown Error/timeout → <flakyError>-ребёнок testcase;
 *   - флак с упавшим expect(...)  → <flakyFailure>-ребёнок testcase
 *     (контрольная проба ревьюера: прежний парсер считал только flakyError —
 *     assertion-флаки обходили гейт);
 *   - стабильно проходящий → testcase без детей;
 *   - стабильно падающий → <error>/<failure> (+ <rerunError> на попытки).
 *
 * Usage: node scripts/parse-e2e-flaky.mjs <results.xml> [--budget N]
 *   Выход: 0 — в бюджете; 1 — превышение ИЛИ битый/чужой XML.
 */
import { readFileSync } from 'node:fs'
import { SaxesParser } from 'saxes'

/**
 * @param {string} xml — содержимое results.xml
 * @returns {string[]} — имена (classname::name) flaky-тестов
 */
export function parseFlaky(xml) {
  const flaky = []
  let depth = 0
  let rootSeen = false
  let rootClosed = false
  let testcase = null

  const parser = new SaxesParser({ xmlns: false })
  parser.on('error', (error) => {
    throw error
  })
  parser.on('opentag', (tag) => {
    if (depth === 0) {
      if (rootSeen || (tag.name !== 'testsuites' && tag.name !== 'testsuite')) {
        throw new Error(`неожиданный junit root: <${tag.name}>`)
      }
      rootSeen = true
    }

    if (tag.name === 'testcase') {
      if (testcase !== null) throw new Error('вложенный <testcase> недопустим')
      testcase = {
        depth,
        name: String(tag.attributes.name ?? ''),
        classname: String(tag.attributes.classname ?? ''),
        isFlaky: false,
      }
    } else if (
      testcase !== null &&
      depth === testcase.depth + 1 &&
      (tag.name === 'flakyError' || tag.name === 'flakyFailure')
    ) {
      testcase.isFlaky = true
    }
    depth += 1
  })
  parser.on('closetag', () => {
    depth -= 1
    if (testcase !== null && depth === testcase.depth) {
      if (testcase.isFlaky) {
        flaky.push(testcase.classname ? `${testcase.classname}::${testcase.name}` : testcase.name)
      }
      testcase = null
    }
    if (depth === 0) rootClosed = true
  })

  parser.write(xml).close()
  if (!rootSeen || !rootClosed || depth !== 0 || testcase !== null) {
    throw new Error('неполный junit-документ')
  }
  return flaky
}

/** Полная структурная XML-проверка с обязательным JUnit root. */
export function validateJunit(xml) {
  try {
    parseFlaky(xml)
    return true
  } catch {
    return false
  }
}

function main() {
  const args = process.argv.slice(2)
  const file = args[0]
  const budgetIdx = args.indexOf('--budget')
  const budget = budgetIdx !== -1 ? Number(args[budgetIdx + 1]) : 2
  if (!file || !Number.isSafeInteger(budget) || budget < 0) {
    console.error('usage: node parse-e2e-flaky.mjs <results.xml> [--budget N]')
    process.exit(1)
  }
  let xml
  try {
    xml = readFileSync(file, 'utf-8')
  } catch (err) {
    console.error(`::error::не прочитан ${file}: ${err}`)
    process.exit(1)
  }
  let flaky
  try {
    flaky = parseFlaky(xml)
  } catch (err) {
    console.error(`::error::${file} — битый junit XML: ${err}`)
    process.exit(1)
  }
  console.log(`flaky/retried тестов: ${flaky.length} (бюджет: ${budget})`)
  for (const name of flaky) console.log(`  FLAKY ${name}`)
  if (flaky.length > budget) {
    console.error(
      `::error::flaky-бюджет превышен (${flaky.length} > ${budget}): стабилизируй тесты или разбери нагрузку раннера`,
    )
    process.exit(1)
  }
}

// CLI только при прямом запуске; при импорте из vitest main() не зовётся
if (import.meta.url === `file://${process.argv[1]}`) {
  main()
}
