/**
 * Unit-тесты парсера e2e-flaky (audit-review follow-up², P1).
 *
 * Фикстуры — РЕАЛЬНЫЙ формат Playwright junit-репортера (includeRetries: true),
 * снятый с живого прогона. Флак-признака ДВА (контрольная проба ревьюера):
 * <flakyError> — thrown Error/timeout; <flakyFailure> — упавший expect(...),
 * восстановившийся ретраем. Прежний парсер знал только flakyError —
 * assertion-флаки обходили гейт.
 */
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'
import { describe, it, expect } from 'vitest'
import { parseFlaky, validateJunit } from '../../scripts/parse-e2e-flaky.mjs'

const SCRIPT = resolve(dirname(fileURLToPath(import.meta.url)), '../../scripts/parse-e2e-flaky.mjs')

function runCli(xml: string, budget = '2') {
  const dir = mkdtempSync(join(tmpdir(), 'portal-flaky-parser-'))
  const report = join(dir, 'results.xml')
  writeFileSync(report, xml, 'utf8')
  try {
    return spawnSync(process.execPath, [SCRIPT, report, '--budget', budget], {
      encoding: 'utf8',
    })
  } finally {
    rmSync(dir, { recursive: true, force: true })
  }
}

const REAL_FLAKY = `<?xml version="1.0"?>
<testsuites tests="2" failures="0" errors="0">
<testsuite name="s.spec.ts" tests="2">
<testcase name="passes on second attempt" classname="s.spec.ts" time="0.002">
<flakyError message="first attempt fails" type="Error">
</flakyError>
</testcase>
<testcase name="always passes" classname="s.spec.ts" time="0.001">
</testcase>
</testsuite>
</testsuites>`

const REAL_BROKEN_WITH_RETRIES = `<?xml version="1.0"?>
<testsuites tests="1" failures="0" errors="1">
<testsuite name="s.spec.ts" tests="1">
<testcase name="always fails" classname="s.spec.ts" time="0.003">
<rerunError message="boom" type="Error"></rerunError>
<rerunError message="boom" type="Error"></rerunError>
<error message="boom" type="Error"></error>
</testcase>
</testsuite>
</testsuites>`

const REAL_THREE_FLAKY = `<?xml version="1.0"?>
<testsuites tests="4">
<testsuite name="a.spec.ts" tests="2">
<testcase name="f1" classname="a.spec.ts"><flakyError message="x"></flakyError></testcase>
<testcase name="stable" classname="a.spec.ts"></testcase>
</testsuite>
<testsuite name="b.spec.ts" tests="2">
<testcase name="f2" classname="b.spec.ts"><flakyError message="y"></flakyError></testcase>
<testcase name="f3" classname="b.spec.ts"><flakyError message="z"></flakyError></testcase>
</testsuite>
</testsuites>`

describe('parseFlaky (реальный формат Playwright junit)', () => {
  it('0 flaky: только стабильные проходы и падения с ретраями', () => {
    expect(parseFlaky(REAL_BROKEN_WITH_RETRIES)).toEqual([])
    expect(parseFlaky('<testsuites/>')).toEqual([])
  })

  it('1 flaky: <flakyError> найден, имя classname::name', () => {
    expect(parseFlaky(REAL_FLAKY)).toEqual(['s.spec.ts::passes on second attempt'])
  })

  it('2 flaky через разные suites', () => {
    const two = REAL_THREE_FLAKY.replace(
      /<testcase name="f3"[^]*?<\/testcase>/,
      '<testcase name="f3-stable" classname="b.spec.ts"></testcase>',
    )
    expect(parseFlaky(two)).toEqual(['a.spec.ts::f1', 'b.spec.ts::f2'])
  })

  it('3 flaky — бюджет 2 должен пробиваться (счётчик точный)', () => {
    expect(parseFlaky(REAL_THREE_FLAKY)).toEqual([
      'a.spec.ts::f1',
      'b.spec.ts::f2',
      'b.spec.ts::f3',
    ])
  })

  it('self-closing testcase без детей не ломает парсер', () => {
    const xml = `<testsuites><testsuite><testcase name="x" classname="c"/></testsuite></testsuites>`
    expect(parseFlaky(xml)).toEqual([])
  })

  // ── flakyFailure: упавший expect, прошедший ретраем (проба ревьюера) ──────

  it('assertion-флак <flakyFailure> считается (контрпример ревьюера)', () => {
    const xml = `<?xml version="1.0"?>
<testsuites tests="2">
<testsuite name="s.spec.ts" tests="2">
<testcase name="assertion-flaky: expect fails then passes" classname="s.spec.ts">
<flakyFailure message="expect(received).toBeGreaterThanOrEqual(expected)" type="Error">
Expected: >= 1
Received: 0
</flakyFailure>
</testcase>
<testcase name="always passes" classname="s.spec.ts"></testcase>
</testsuite>
</testsuites>`
    expect(parseFlaky(xml)).toEqual(['s.spec.ts::assertion-flaky: expect fails then passes'])
  })

  it('смешанные flakyError + flakyFailure считаются оба', () => {
    const xml = `<?xml version="1.0"?>
<testsuites>
<testsuite name="s.spec.ts">
<testcase name="err-flaky" classname="s.spec.ts"><flakyError message="x"></flakyError></testcase>
<testcase name="assert-flaky" classname="s.spec.ts"><flakyFailure message="y"></flakyFailure></testcase>
</testsuite>
</testsuites>`
    expect(parseFlaky(xml)).toEqual(['s.spec.ts::err-flaky', 's.spec.ts::assert-flaky'])
  })
})

describe('validateJunit (битый XML не должен считаться «0 flaky»)', () => {
  it('валидный документ проходит', () => {
    expect(validateJunit(REAL_FLAKY)).toBe(true)
    expect(validateJunit('<testsuites></testsuites>')).toBe(true)
    expect(validateJunit('<testsuite name="x"></testsuite>')).toBe(true)
  })

  it('мусор/пустой/обрезанный XML отклоняются', () => {
    expect(validateJunit('это не архив и не xml')).toBe(false)
    expect(validateJunit('')).toBe(false)
    expect(validateJunit('<html><body>404 page</body></html>')).toBe(false)
    // обрезан посреди testcase — корень не закрыт
    expect(validateJunit(REAL_FLAKY.slice(0, REAL_FLAKY.indexOf('</testcase>')))).toBe(false)
  })

  it('закрытый root с повреждённой внутренней структурой отклоняется', () => {
    const malformed = '<testsuites><testcase name="broken"><flakyFailure></testsuites>'
    expect(validateJunit(malformed)).toBe(false)
    expect(() => parseFlaky(malformed)).toThrow()
  })

  it('валидный self-closing root принимается', () => {
    expect(validateJunit('<testsuites/>')).toBe(true)
  })
})

describe('parse-e2e-flaky CLI', () => {
  it('0/2 flaky проходят, 3 flaky превышают бюджет 2', () => {
    expect(runCli(REAL_BROKEN_WITH_RETRIES).status).toBe(0)
    const two = REAL_THREE_FLAKY.replace(
      /<testcase name="f3"[^]*?<\/testcase>/,
      '<testcase name="f3-stable" classname="b.spec.ts"></testcase>',
    )
    expect(runCli(two).status).toBe(0)
    const over = runCli(REAL_THREE_FLAKY)
    expect(over.status).toBe(1)
    expect(over.stderr).toContain('flaky-бюджет превышен (3 > 2)')
  })

  it('битый XML завершается fail-closed', () => {
    const result = runCli('<testsuites><testcase name="broken"><flakyFailure></testsuites>')
    expect(result.status).toBe(1)
    expect(result.stderr).toContain('битый junit XML')
  })

  it('невалидные бюджеты отклоняются', () => {
    for (const budget of ['-1', '2.5', 'Infinity']) {
      expect(runCli(REAL_FLAKY, budget).status).toBe(1)
    }
  })

  it('отсутствующий файл завершается fail-closed', () => {
    const result = spawnSync(process.execPath, [SCRIPT, '/definitely/missing/results.xml'], {
      encoding: 'utf8',
    })
    expect(result.status).toBe(1)
    expect(result.stderr).toContain('не прочитан')
  })
})
