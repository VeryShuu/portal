/**
 * Unit-тесты useParticipantAbsenceSync: бейджи отсутствия выбранных участников
 * пересчитываются на дату встречи (как в сводке), а не «на сегодня».
 *
 * Покрытие:
 * - стартовый sync: запрос с локальной датой встречи + нормализация регистра;
 * - смена даты → перезапрос, устаревший бейдж стирается (явный null);
 * - внешние участники исключаются, пустой список — без запроса;
 * - ошибка сети не трогает предыдущие бейджи;
 * - опоздавший ответ (гонка при смене даты) отбрасывается;
 * - при закрытом диалоге (enabled=false) запросы не шлются;
 * - удалённый во время запроса участник не воскрешается.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { defineComponent, h, ref } from 'vue'
import { mount } from '@vue/test-utils'

import type { FormState } from '../../src/components/meetings/meeting-form/composables/useMeetingFormState'
import type { InvitedAbsence, InvitedUser } from '../../src/api/meetings'

const fetchParticipantAbsences = vi.fn()

vi.mock('../../src/api/meetings', () => ({
  fetchParticipantAbsences: (...args: unknown[]) => fetchParticipantAbsences(...args),
}))

// Локальные конструкторы даты → toLocalDateStr даёт ту же дату в любом TZ тест-раннера.
const AUG_20 = new Date(2026, 7, 20, 10, 0).getTime()
const SEP_01 = new Date(2026, 8, 1, 10, 0).getTime()

const VACATION: InvitedAbsence = { category: 'vacation', start_date: '2026-08-18', end_date: '2026-08-25' }
const SICK: InvitedAbsence = { category: 'sick', start_date: '2026-08-19', end_date: '2026-08-19' }

function makeUser(email: string, overrides: Partial<InvitedUser> = {}): InvitedUser {
  return { user_id: `id-${email}`, full_name: email, email, source: 'keycloak', ...overrides }
}

function makeForm(overrides: Partial<FormState> = {}): FormState {
  return {
    title: 'T',
    description: '',
    room_ids: [],
    invited_users: [],
    recurrence: null,
    apply_to: 'this',
    start_time: AUG_20,
    end_time: AUG_20 + 3_600_000,
    ...overrides,
  }
}

async function setup(initial: FormState, enabled: () => boolean = () => true) {
  const mod = await import('../../src/components/meetings/meeting-form/composables/useParticipantAbsenceSync')
  const form = ref<FormState>(initial)
  mount(defineComponent({
    setup() {
      mod.useParticipantAbsenceSync(form, enabled)
      return () => h('div')
    },
  }))
  return { form }
}

describe('useParticipantAbsenceSync', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    fetchParticipantAbsences.mockReset()
    fetchParticipantAbsences.mockResolvedValue({})
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('на старте запрашивает отсутствия на локальную дату встречи и проставляет бейджи', async () => {
    fetchParticipantAbsences.mockResolvedValue({ 'a@x.com': VACATION })
    const { form } = await setup(
      makeForm({ invited_users: [makeUser('A@X.com'), makeUser('b@x.com')] }),
    )

    await vi.advanceTimersByTimeAsync(310)

    // Email в запросе — как в списке (нормализация на бэке), дата — локальная.
    expect(fetchParticipantAbsences).toHaveBeenCalledTimes(1)
    expect(fetchParticipantAbsences).toHaveBeenCalledWith(['A@X.com', 'b@x.com'], '2026-08-20')
    expect(form.value.invited_users[0].absence).toEqual(VACATION)
    expect(form.value.invited_users[1].absence).toBeNull()
  })

  it('при смене даты перезапрашивает и стирает бейдж, если на новую дату отсутствия нет', async () => {
    fetchParticipantAbsences.mockResolvedValueOnce({ 'a@x.com': SICK })
    const { form } = await setup(
      makeForm({ invited_users: [makeUser('a@x.com', { absence: SICK })] }),
    )
    await vi.advanceTimersByTimeAsync(310)
    expect(form.value.invited_users[0].absence).toEqual(SICK)

    form.value.start_time = SEP_01
    fetchParticipantAbsences.mockResolvedValueOnce({})
    await vi.advanceTimersByTimeAsync(310)

    expect(fetchParticipantAbsences).toHaveBeenLastCalledWith(['a@x.com'], '2026-09-01')
    expect(form.value.invited_users[0].absence).toBeNull()
  })

  it('внешние участники исключаются из запроса, пустой список — без запроса', async () => {
    await setup(makeForm({ invited_users: [makeUser('ext@y.com', { source: 'external' })] }))
    await vi.advanceTimersByTimeAsync(310)
    expect(fetchParticipantAbsences).not.toHaveBeenCalled()

    const { form } = await setup(
      makeForm({ invited_users: [makeUser('a@x.com'), makeUser('ext@y.com', { source: 'external' })] }),
    )
    await vi.advanceTimersByTimeAsync(310)
    expect(fetchParticipantAbsences).toHaveBeenCalledWith(['a@x.com'], '2026-08-20')
    expect(form.value.invited_users).toHaveLength(2)
  })

  it('при ошибке сети оставляет предыдущие бейджи', async () => {
    fetchParticipantAbsences.mockRejectedValue(new Error('network down'))
    const { form } = await setup(
      makeForm({ invited_users: [makeUser('a@x.com', { absence: VACATION })] }),
    )

    await vi.advanceTimersByTimeAsync(310)

    expect(form.value.invited_users[0].absence).toEqual(VACATION)
  })

  it('опоздавший ответ отбрасывается (гонка при смене даты)', async () => {
    let resolveFirst!: (v: Record<string, InvitedAbsence>) => void
    const first = new Promise<Record<string, InvitedAbsence>>(resolve => {
      resolveFirst = resolve
    })
    fetchParticipantAbsences.mockReturnValueOnce(first)
    fetchParticipantAbsences.mockResolvedValueOnce({})

    const { form } = await setup(
      makeForm({ invited_users: [makeUser('a@x.com', { absence: SICK })] }),
    )
    // Первый запрос (на 2026-08-20) улетел и висит.
    await vi.advanceTimersByTimeAsync(310)

    form.value.start_time = SEP_01
    // Второй запрос (на 2026-09-01) улетел и разрешился пустым.
    await vi.advanceTimersByTimeAsync(310)
    expect(form.value.invited_users[0].absence).toBeNull()

    // Первый ответ пришёл позже — не должен перезаписать результат по новой дате.
    resolveFirst({ 'a@x.com': VACATION })
    await vi.advanceTimersByTimeAsync(0)
    expect(form.value.invited_users[0].absence).toBeNull()
  })

  it('пока диалог закрыт (enabled=false), запросы не шлёт', async () => {
    let open = false
    const { form } = await setup(
      makeForm({ invited_users: [makeUser('a@x.com')] }),
      () => open,
    )

    await vi.advanceTimersByTimeAsync(310)
    expect(fetchParticipantAbsences).not.toHaveBeenCalled()

    open = true
    form.value.start_time = SEP_01
    await vi.advanceTimersByTimeAsync(310)
    expect(fetchParticipantAbsences).toHaveBeenCalledTimes(1)
    expect(fetchParticipantAbsences).toHaveBeenCalledWith(['a@x.com'], '2026-09-01')
  })

  it('участник, удалённый во время запроса, не воскрешается', async () => {
    let resolveFirst!: (v: Record<string, InvitedAbsence>) => void
    const first = new Promise<Record<string, InvitedAbsence>>(resolve => {
      resolveFirst = resolve
    })
    fetchParticipantAbsences.mockReturnValueOnce(first)

    const { form } = await setup(
      makeForm({ invited_users: [makeUser('a@x.com'), makeUser('b@x.com')] }),
    )
    await vi.advanceTimersByTimeAsync(310)

    // Пользователь удалил b@x.com, пока ответ был в полёте.
    form.value.invited_users = [form.value.invited_users[0]]
    resolveFirst({ 'a@x.com': VACATION, 'b@x.com': VACATION })
    await vi.advanceTimersByTimeAsync(0)

    expect(form.value.invited_users).toHaveLength(1)
    expect(form.value.invited_users[0].absence).toEqual(VACATION)
  })
})
