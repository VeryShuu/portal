import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useHighlight } from '../../src/composables/useHighlight'

describe('useHighlight', () => {
  it('returns escaped text without <mark> when query is empty', () => {
    const hl = useHighlight(ref(''))
    expect(hl('Иванов Иван')).toBe('Иванов Иван')
    expect(hl('')).toBe('')
    expect(hl(null)).toBe('')
    expect(hl(undefined)).toBe('')
  })

  it('escapes HTML in input even without query', () => {
    const hl = useHighlight(ref(''))
    const out = hl('<script>alert(1)</script>')
    expect(out).not.toContain('<script>')
    expect(out).toContain('&lt;script&gt;')
  })

  it('wraps matches with <mark class="staff-hl"> case-insensitively', () => {
    const hl = useHighlight(ref('иван'))
    const out = hl('Иванов Иван')
    // первое и второе вхождение должны быть в <mark>
    expect(out).toMatch(/<mark class="staff-hl">Иван<\/mark>/)
    expect((out.match(/<mark class="staff-hl">/g) || []).length).toBe(2)
  })

  it('escapes HTML inside the query (XSS protection)', () => {
    const hl = useHighlight(ref('<img src=x onerror=alert(1)>'))
    const out = hl('safe text')
    expect(out).not.toContain('<img')
    expect(out).not.toContain('onerror')
  })

  it('escapes HTML in input that also matches the query', () => {
    const hl = useHighlight(ref('script'))
    const out = hl('<script>')
    expect(out).not.toContain('<script>')
    // буквальное "script" внутри экранированной строки должно быть подсвечено
    expect(out).toContain('<mark class="staff-hl">script</mark>')
  })

  it('treats regex metacharacters in query as literal', () => {
    const hl = useHighlight(ref('a.b'))
    expect(hl('xaxbx')).toBe('xaxbx')
    expect(hl('xa.bx')).toContain('<mark class="staff-hl">a.b</mark>')
  })

  it('trims whitespace-only query', () => {
    const hl = useHighlight(ref('   '))
    expect(hl('hello')).toBe('hello')
  })

  it('does not leak <script> tag for malicious input even when query matches', () => {
    const hl = useHighlight(ref('alert'))
    const out = hl('<script>alert(1)</script>')
    expect(out).not.toMatch(/<script>/i)
    expect(out).toContain('&lt;script&gt;')
    expect(out).toContain('<mark class="staff-hl">alert</mark>')
  })

  it('escapes <img onerror> payload in input', () => {
    const hl = useHighlight(ref(''))
    const out = hl('<img src=x onerror=alert(1)>')
    expect(out).not.toContain('<img')
    expect(out).toContain('&lt;img')
    expect(out).toContain('&gt;')
  })

  it('escapes quotes and angle brackets in the input', () => {
    const hl = useHighlight(ref(''))
    const out = hl('"><svg onload=alert(1)>')
    expect(out).not.toContain('<svg')
    expect(out).toContain('&quot;')
    expect(out).toContain('&gt;')
    expect(out).toContain('&lt;svg')
  })

  it('handles JNDI-style payloads as plain text', () => {
    const hl = useHighlight(ref(''))
    const out = hl('${jndi:ldap://x}')
    expect(out).toBe('${jndi:ldap://x}')
  })

  it('handles multiline input correctly', () => {
    const hl = useHighlight(ref('foo'))
    const out = hl('foo\nbar\nfoo')
    expect(out.split('\n').length).toBe(3)
    expect((out.match(/<mark class="staff-hl">foo<\/mark>/g) || []).length).toBe(2)
  })

  it('highlights matches inside HTML entities (e.g. amp in &amp;)', () => {
    const hl = useHighlight(ref('amp'))
    const out = hl('a & b')
    expect(out).toContain('<mark class="staff-hl">amp</mark>')
    expect(out).toContain('&')
    expect(out).toContain(';')
  })

  it('reacts to ref changes (returns up-to-date highlighter)', () => {
    const q = ref('foo')
    const hl = useHighlight(q)
    expect(hl('foobar')).toContain('<mark')
    q.value = 'baz'
    expect(hl('foobar')).toBe('foobar')
    expect(hl('bazbar')).toContain('<mark')
  })
})
