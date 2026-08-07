import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { InvitedAbsence } from '../api/meetings'
import { formatDateShort } from '../utils/formatDate'

/**
 * Текстовая подпись отсутствия участника (отпуск/болезнь/командировка · до {дата}).
 *
 * Общая логика для ParticipantPicker (форма) и MeetingsList (детали), повторяет
 * формат справочника сотрудников (StaffRow.vue): «В отпуске / отгуле · до 15 авг».
 * Категории переиспользуют существующие i18n-ключи `users.presence.*`.
 *
 * Возвращает функцию-форматтер + готовый класс цвета для бейджа.
 */
export function usePresenceLabel() {
  const { t, locale } = useI18n()

  const presenceLabel = (absence: InvitedAbsence | null | undefined): string => {
    if (!absence) return ''
    const label = t(`users.presence.${absence.category}`)
    const until = absence.end_date
    if (!until) return label
    return `${label} · ${t('users.presence.until', { date: formatDateShort(until, locale.value) })}`
  }

  /** CSS-класс цвета по категории (использует --presence-ring-* токены). */
  const presenceClass = (absence: InvitedAbsence | null | undefined): string => {
    if (!absence) return ''
    return `presence--${absence.category}`
  }

  return { presenceLabel, presenceClass, locale: computed(() => locale.value) }
}
