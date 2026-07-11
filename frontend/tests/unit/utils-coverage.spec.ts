import { describe, it, expect, vi } from 'vitest'

describe('src/utils/formatDate', () => {
  it('formats date in Russian locale', async () => {
    const { formatDate } = await import('../../src/utils/formatDate')
    const result = formatDate('2024-01-15T00:00:00Z', 'ru')
    expect(result).toMatch(/2024/)
    expect(result).toMatch(/15/)
  })

  it('formats date in English locale', async () => {
    const { formatDate } = await import('../../src/utils/formatDate')
    const result = formatDate('2024-06-20T00:00:00Z', 'en')
    expect(result).toMatch(/2024/)
  })

  it('formatDateShort in Russian locale', async () => {
    const { formatDateShort } = await import('../../src/utils/formatDate')
    const result = formatDateShort('2024-03-10T00:00:00Z', 'ru')
    expect(result).toBeTruthy()
    expect(typeof result).toBe('string')
  })

  it('formatDateShort in English locale', async () => {
    const { formatDateShort } = await import('../../src/utils/formatDate')
    const result = formatDateShort('2024-12-25T00:00:00Z', 'en')
    expect(result).toBeTruthy()
    expect(typeof result).toBe('string')
  })
})

describe('src/utils/formatSize', () => {
  it('returns empty string for null', async () => {
    const { formatSize } = await import('../../src/utils/formatSize')
    expect(formatSize(null)).toBe('')
  })

  it('returns empty string for undefined', async () => {
    const { formatSize } = await import('../../src/utils/formatSize')
    expect(formatSize(undefined)).toBe('')
  })

  it('formats bytes', async () => {
    const { formatSize } = await import('../../src/utils/formatSize')
    expect(formatSize(512)).toBe('512 B')
  })

  it('formats kilobytes', async () => {
    const { formatSize } = await import('../../src/utils/formatSize')
    expect(formatSize(2048)).toBe('2.0 KB')
  })

  it('formats megabytes', async () => {
    const { formatSize } = await import('../../src/utils/formatSize')
    expect(formatSize(3 * 1024 * 1024)).toBe('3.0 MB')
  })

  it('formats gigabytes', async () => {
    const { formatSize } = await import('../../src/utils/formatSize')
    expect(formatSize(2 * 1024 * 1024 * 1024)).toBe('2.00 GB')
  })

  it('formats 0 bytes', async () => {
    const { formatSize } = await import('../../src/utils/formatSize')
    expect(formatSize(0)).toBe('0 B')
  })
})

describe('src/utils/markdown', () => {
  it('mdSafe renders markdown without html', async () => {
    const { mdSafe } = await import('../../src/utils/markdown')
    const result = mdSafe.render('**bold** text')
    expect(result).toContain('<strong>bold</strong>')
  })

  it('mdSafe strips HTML tags', async () => {
    const { mdSafe } = await import('../../src/utils/markdown')
    const result = mdSafe.render('<script>alert(1)</script>')
    expect(result).not.toContain('<script>')
  })

  it('mdUnsafe renders markdown with html', async () => {
    const { mdUnsafe } = await import('../../src/utils/markdown')
    const result = mdUnsafe.render('<em>italic</em>')
    expect(result).toContain('<em>italic</em>')
  })
})

describe('src/utils/parseApiError', () => {
  const t = vi.fn((key: string) => key)

  beforeEach(() => {
    t.mockImplementation((key: string) => key)
  })

  it('returns generic error for null/undefined', async () => {
    const { parseApiError } = await import('../../src/utils/parseApiError')
    expect(parseApiError(null, t as any)).toBe('errors.generic')
    expect(parseApiError(undefined, t as any)).toBe('errors.generic')
    expect(parseApiError('string', t as any)).toBe('errors.generic')
  })

  it('returns unauthorized message for 401', async () => {
    const { parseApiError } = await import('../../src/utils/parseApiError')
    expect(parseApiError({ status: 401 }, t as any)).toBe('errors.unauthorized')
    expect(parseApiError({ statusCode: 401 }, t as any)).toBe('errors.unauthorized')
  })

  it('returns forbidden message for 403', async () => {
    const { parseApiError } = await import('../../src/utils/parseApiError')
    expect(parseApiError({ status: 403 }, t as any)).toBe('errors.forbidden')
  })

  // FE-4: ранее bare `t('errors.generic')` показывал «Что-то пошло не так»
  // независимо от ответа backend. После перехода на parseApiError(e, t)
  // пользователь видит домен-специфичное сообщение для каждого статуса.
  it.each([
    ['401 → unauthorized', { status: 401 }, 'errors.unauthorized'],
    ['403 → forbidden', { status: 403 }, 'errors.forbidden'],
    ['500 with detail → backend detail', { status: 500, data: { detail: 'DB is down' } }, 'DB is down'],
  ])('surfaces backend context for %s (FE-4 regression guard)', async (_label, err, expected) => {
    const { parseApiError } = await import('../../src/utils/parseApiError')
    expect(parseApiError(err, t as any)).toBe(expected)
  })

  it('returns string detail directly', async () => {
    const { parseApiError } = await import('../../src/utils/parseApiError')
    const err = { data: { detail: 'Email already in use' } }
    expect(parseApiError(err, t as any)).toBe('Email already in use')
  })

  it('returns generic for empty string detail', async () => {
    const { parseApiError } = await import('../../src/utils/parseApiError')
    const err = { data: { detail: '   ' } }
    expect(parseApiError(err, t as any)).toBe('errors.generic')
  })

  it('returns generic for empty pydantic array', async () => {
    const { parseApiError } = await import('../../src/utils/parseApiError')
    const err = { data: { detail: [] } }
    expect(parseApiError(err, t as any)).toBe('errors.generic')
  })

  it('formats pydantic validation error with field and message', async () => {
    const { parseApiError } = await import('../../src/utils/parseApiError')
    t.mockImplementation((key: string) => key)
    const err = {
      status: 422,
      data: {
        detail: [{ loc: ['body', 'email'], msg: 'field required', type: 'missing' }],
      },
    }
    const result = parseApiError(err, t as any)
    expect(result).toBeTruthy()
    expect(typeof result).toBe('string')
  })

  it('formats pydantic error without loc', async () => {
    const { parseApiError } = await import('../../src/utils/parseApiError')
    const err = {
      data: { detail: [{ msg: 'value error', type: 'value_error' }] },
    }
    const result = parseApiError(err, t as any)
    expect(typeof result).toBe('string')
  })

  it('does NOT surface message for arbitrary Error (internal detail leak)', async () => {
    const { parseApiError } = await import('../../src/utils/parseApiError')
    // Plain Error / plain object: message is an implementation detail → generic.
    expect(parseApiError({ message: 'Network error' }, t as any)).toBe('errors.generic')
    expect(parseApiError(new Error('internal assert'), t as any)).toBe('errors.generic')
  })

  it('surfaces message for ofetch FetchError (HTTP response summary)', async () => {
    const { parseApiError } = await import('../../src/utils/parseApiError')
    const err = { name: 'FetchError', message: 'POST /api/v1/news: 500' }
    expect(parseApiError(err, t as any)).toBe('POST /api/v1/news: 500')
  })

  it('ignores message that looks like HTTP error code', async () => {
    const { parseApiError } = await import('../../src/utils/parseApiError')
    const err = { message: '[404] Not Found' }
    expect(parseApiError(err, t as any)).toBe('errors.generic')
  })

  it('returns generic for empty message', async () => {
    const { parseApiError } = await import('../../src/utils/parseApiError')
    const err = { message: '   ' }
    expect(parseApiError(err, t as any)).toBe('errors.generic')
  })

  it('filters non-object items from pydantic detail array', async () => {
    const { parseApiError } = await import('../../src/utils/parseApiError')
    const err = {
      data: { detail: [null, undefined, 'string'] },
    }
    const result = parseApiError(err, t as any)
    expect(result).toBe('errors.generic')
  })

  it('handles pydantic loc with only reserved words', async () => {
    const { parseApiError } = await import('../../src/utils/parseApiError')
    const err = {
      data: {
        detail: [{ loc: ['body', 'query'], msg: 'invalid', type: 'value_error' }],
      },
    }
    const result = parseApiError(err, t as any)
    expect(typeof result).toBe('string')
  })

  it('uses field translation when available', async () => {
    const { parseApiError } = await import('../../src/utils/parseApiError')
    t.mockImplementation((key: string) => {
      if (key === 'errors.fields.email') return 'Email'
      if (key === 'errors.validation.missing') return 'обязательное поле'
      return key
    })
    const err = {
      data: {
        detail: [{ loc: ['body', 'email'], msg: 'field required', type: 'missing' }],
      },
    }
    const result = parseApiError(err, t as any)
    expect(result).toContain('Email')
    expect(result).toContain('обязательное поле')
  })

  it('uses custom fallback instead of errors.generic for unknown formats', async () => {
    const { parseApiError } = await import('../../src/utils/parseApiError')
    expect(parseApiError(null, t as any, 'custom.fallback')).toBe('custom.fallback')
    expect(parseApiError({}, t as any, 'custom.fallback')).toBe('custom.fallback')
    expect(parseApiError({ data: { detail: [] } }, t as any, 'custom.fallback')).toBe(
      'custom.fallback',
    )
    expect(
      parseApiError({ data: { detail: [null] } }, t as any, 'custom.fallback'),
    ).toBe('custom.fallback')
  })

  it('custom fallback does not override status/detail-derived messages', async () => {
    const { parseApiError } = await import('../../src/utils/parseApiError')
    expect(parseApiError({ status: 401 }, t as any, 'custom.fallback')).toBe(
      'errors.unauthorized',
    )
    expect(parseApiError({ status: 403 }, t as any, 'custom.fallback')).toBe(
      'errors.forbidden',
    )
    expect(
      parseApiError({ data: { detail: 'Boom' } }, t as any, 'custom.fallback'),
    ).toBe('Boom')
  })
})

describe('src/utils/download', () => {
  it('triggerDownload creates anchor and clicks it', async () => {
    const { triggerDownload } = await import('../../src/utils/download')
    const click = vi.fn()
    const anchor = { href: '', target: '', rel: '', click } as unknown as HTMLAnchorElement
    vi.spyOn(document, 'createElement').mockReturnValueOnce(anchor)
    triggerDownload('https://example.com/file.zip', { target: '_blank', rel: 'noopener' })
    expect(anchor.href).toBe('https://example.com/file.zip')
    expect(anchor.target).toBe('_blank')
    expect(anchor.rel).toBe('noopener')
    expect(click).toHaveBeenCalledOnce()
  })

  it('triggerDownload works without options', async () => {
    const { triggerDownload } = await import('../../src/utils/download')
    const click = vi.fn()
    const anchor = { href: '', target: '', rel: '', click } as unknown as HTMLAnchorElement
    vi.spyOn(document, 'createElement').mockReturnValueOnce(anchor)
    triggerDownload('https://example.com/file.pdf')
    expect(anchor.href).toBe('https://example.com/file.pdf')
    expect(click).toHaveBeenCalledOnce()
  })
})

describe('src/utils/coverFocal', () => {
  it('clamps and rounds coordinates into 0..100', async () => {
    const { clampFocalCoord } = await import('../../src/utils/coverFocal')
    expect(clampFocalCoord(-10)).toBe(0)
    expect(clampFocalCoord(150)).toBe(100)
    expect(clampFocalCoord(42.6)).toBe(43)
    expect(clampFocalCoord(Number.NaN)).toBe(50)
  })

  it('builds object-position string, defaulting null/undefined to center', async () => {
    const { focalObjectPosition } = await import('../../src/utils/coverFocal')
    expect(focalObjectPosition(0, 100)).toBe('0% 100%')
    expect(focalObjectPosition(null, null)).toBe('50% 50%')
    expect(focalObjectPosition(undefined, 30)).toBe('50% 30%')
    expect(focalObjectPosition(150, -5)).toBe('100% 0%')
  })

  it('clamps and rounds zoom into 100..300', async () => {
    const { clampFocalZoom } = await import('../../src/utils/coverFocal')
    expect(clampFocalZoom(50)).toBe(100)
    expect(clampFocalZoom(500)).toBe(300)
    expect(clampFocalZoom(142.6)).toBe(143)
    expect(clampFocalZoom(Number.NaN)).toBe(100)
  })

  it('builds focal image style with transform around focal point', async () => {
    const { focalImageStyle } = await import('../../src/utils/coverFocal')
    expect(focalImageStyle(null, null, null)).toEqual({
      objectPosition: '50% 50%',
      transform: 'none',
      transformOrigin: '50% 50%',
    })
    expect(focalImageStyle(20, 80, 100)).toEqual({
      objectPosition: '20% 80%',
      transform: 'none',
      transformOrigin: '20% 80%',
    })
    expect(focalImageStyle(20, 80, 200)).toEqual({
      objectPosition: '20% 80%',
      transform: 'scale(2)',
      transformOrigin: '20% 80%',
    })
    expect(focalImageStyle(150, -5, 500)).toEqual({
      objectPosition: '100% 0%',
      transform: 'scale(3)',
      transformOrigin: '100% 0%',
    })
  })
})
