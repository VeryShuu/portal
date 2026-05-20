export type MeetingsErrorCode =
  | 'START_TIME_IN_PAST'
  | 'END_BEFORE_START'
  | 'BOOKING_CONFLICT'
  | null

type ErrorLike = {
  data?: {
    code?: string
    detail?: unknown
    conflicts?: unknown
  }
  status?: number
}

export function mapMeetingsError(err: unknown): MeetingsErrorCode {
  if (!err || typeof err !== 'object') return null
  const e = err as ErrorLike

  if (e.data?.code === 'START_TIME_IN_PAST') return 'START_TIME_IN_PAST'
  if (Array.isArray(e.data?.conflicts)) return 'BOOKING_CONFLICT'

  const detail = e.data?.detail
  if (Array.isArray(detail)) {
    for (const item of detail as Array<{ msg?: string; loc?: unknown[] }>) {
      const msg = typeof item?.msg === 'string' ? item.msg : ''
      if (msg.includes('[START_TIME_IN_PAST]')) return 'START_TIME_IN_PAST'
      if (msg.includes('end_time must be after start_time')) return 'END_BEFORE_START'
    }
  }
  return null
}
