import type { ComposerTranslation } from 'vue-i18n'

type PydanticError = {
  loc?: (string | number)[]
  msg?: string
  type?: string
  ctx?: Record<string, unknown>
}

type ApiErrorLike = {
  data?: {
    detail?: string | PydanticError[] | Record<string, unknown>
  }
  status?: number
  statusCode?: number
  message?: string
}

function fieldKey(loc: (string | number)[] | undefined): string | null {
  if (!loc || loc.length === 0) return null
  for (let i = loc.length - 1; i >= 0; i--) {
    const part = loc[i]
    if (typeof part === 'string' && part !== 'body' && part !== 'query' && part !== 'path') {
      return part
    }
  }
  return null
}

function translateField(t: ComposerTranslation, key: string | null): string | null {
  if (!key) return null
  const i18nKey = `errors.fields.${key}`
  const translated = t(i18nKey)
  return translated === i18nKey ? null : translated
}

function translateValidation(
  t: ComposerTranslation,
  type: string | undefined,
  msg: string | undefined,
  ctx: Record<string, unknown> | undefined,
): string {
  if (type) {
    const i18nKey = `errors.validation.${type}`
    const translated = t(i18nKey, (ctx ?? {}) as Record<string, unknown>)
    if (translated !== i18nKey) return translated
  }
  return msg ?? t('errors.validation.invalid')
}

function formatPydanticItem(t: ComposerTranslation, item: PydanticError): string {
  const field = translateField(t, fieldKey(item.loc))
  const msg = translateValidation(t, item.type, item.msg, item.ctx)
  if (field) return `${field}: ${msg}`
  return msg
}

/**
 * Преобразует ошибку от ofetch (FetchError) в человекочитаемое
 * локализованное сообщение. Поддерживает:
 * - Pydantic-ошибки 422 (массив detail с loc/msg/type)
 * - простой string detail (FastAPI HTTPException)
 * - неизвестный формат → fallback на errors.generic
 */
export function parseApiError(err: unknown, t: ComposerTranslation): string {
  if (!err || typeof err !== 'object') return t('errors.generic')

  const e = err as ApiErrorLike
  const status = e.status ?? e.statusCode

  if (status === 401) return t('errors.unauthorized')
  if (status === 403) return t('errors.forbidden')

  const detail = e.data?.detail

  if (Array.isArray(detail)) {
    if (detail.length === 0) return t('errors.generic')
    const messages = detail
      .filter((item): item is PydanticError => !!item && typeof item === 'object')
      .map((item) => formatPydanticItem(t, item))
    if (messages.length === 0) return t('errors.generic')
    return messages.join('\n')
  }

  if (typeof detail === 'string' && detail.trim()) {
    return detail
  }

  if (typeof e.message === 'string' && e.message.trim() && !/^\[\d+\]/.test(e.message)) {
    return e.message
  }

  return t('errors.generic')
}
