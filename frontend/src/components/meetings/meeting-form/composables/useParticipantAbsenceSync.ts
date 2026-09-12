import { watch, type Ref } from 'vue'

import type { InvitedAbsence, InvitedUser } from '../../../../api/meetings'
import { fetchParticipantAbsences } from '../../../../api/meetings'
import { useDebounceFn } from '../../../../composables/useDebounceFn'

const DEBOUNCE_MS = 300

/**
 * Минимальная структурная форма полей, нужных для sync. Отдельный интерфейс, а
 * не импорт ``FormState`` из useMeetingFormState — иначе цикл типов
 * (useMeetingFormState → этот модуль → FormState) ломает вывод типов tsc.
 */
interface AbsenceSyncFormState {
  invited_users: InvitedUser[]
  start_time: number | null
}

/** Локальная дата (YYYY-MM-DD) — та, что пользователь видит в поле «дата». */
function toLocalDateStr(ts: number): string {
  const d = new Date(ts)
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${mm}-${dd}`
}

function isEmployee(u: InvitedUser): boolean {
  return (u.source ?? 'keycloak') !== 'external'
}

function applyAbsences(
  invited: InvitedUser[],
  asked: Set<string>,
  absences: Record<string, InvitedAbsence>,
): void {
  for (const u of invited) {
    if (!isEmployee(u)) continue
    const key = u.email.toLowerCase()
    if (!asked.has(key)) continue
    // Явный null стирает бейдж «на сегодня», если на дату встречи его нет.
    u.absence = absences[key] ?? null
  }
}

/**
 * Бейджи отсутствия выбранных участников — на дату встречи, как в сводке.
 *
 * Search/resolve обогащают absence «на сегодня» (даты встречи в момент поиска
 * ещё нет), а финальная сводка и письма считают на дату встречи — из-за этого
 * бейдж в форме мог не совпадать со сводкой. Watcher пересчитывает бейджи при
 * открытии формы, смене даты и изменении списка участников (debounce 300 мс;
 * гонки отсекаются порядковым номером запроса — опоздавший ответ отбрасывается).
 * Сетевые ошибки глушатся: бейдж — подсказка, сохранение встречи от него не
 * зависит, при сбое остаётся предыдущее значение.
 */
export function useParticipantAbsenceSync(
  form: Ref<AbsenceSyncFormState>,
  enabled: () => boolean,
): void {
  let requestSeq = 0

  async function refresh(): Promise<void> {
    const employees = form.value.invited_users.filter(isEmployee)
    if (!employees.length) return
    const asked = new Set(employees.map(u => u.email.toLowerCase()))
    const onDate = toLocalDateStr(form.value.start_time ?? Date.now())
    const seq = ++requestSeq
    try {
      const absences = await fetchParticipantAbsences(employees.map(u => u.email), onDate)
      if (seq !== requestSeq) return
      applyAbsences(form.value.invited_users, asked, absences)
    } catch {
      // Тихо: бейдж декоративный, ошибки сети не должны мешать бронированию.
    }
  }

  const debounced = useDebounceFn(refresh, DEBOUNCE_MS)

  // Сигнатура без absence — иначе in-place обновление бейджей замкнуло бы watch.
  watch(
    () => [
      form.value.start_time,
      form.value.invited_users.map(u => `${u.source ?? 'keycloak'}:${u.email.toLowerCase()}`).join('|'),
    ],
    () => {
      if (enabled()) debounced()
    },
    { immediate: true },
  )
}
