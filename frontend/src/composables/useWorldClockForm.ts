import { computed, nextTick, ref } from 'vue'
import type { Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage, type SelectOption } from 'naive-ui'
import { useConfirmDialog } from './useConfirmDialog'
import type { ClockCity } from './useWorldClockCities'

const COMMON_TZ = [
  'Europe/Moscow', 'Europe/Kaliningrad', 'Europe/Samara',
  'Asia/Yekaterinburg', 'Asia/Omsk', 'Asia/Krasnoyarsk',
  'Asia/Irkutsk', 'Asia/Yakutsk', 'Asia/Vladivostok',
  'Asia/Magadan', 'Asia/Sakhalin', 'Asia/Kamchatka',
  'Asia/Seoul', 'Asia/Tokyo', 'Asia/Shanghai', 'Asia/Singapore',
  'Asia/Dubai', 'Asia/Almaty', 'Asia/Tashkent',
  'Europe/London', 'Europe/Berlin', 'Europe/Paris',
  'America/New_York', 'America/Los_Angeles', 'UTC',
]

export interface UseWorldClockFormOptions {
  now: Ref<Date>
  cities: Ref<ClockCity[]>
  add: (payload: Omit<ClockCity, 'id'> & { lat?: number; lon?: number }) => void
  update: (id: string, payload: Partial<ClockCity>) => void
  remove: (id: string) => void
  reset: () => void
  reorder: (next: ClockCity[]) => void
  isValidTimezone: (tz: string) => boolean
  onAfterMutation: () => void
}

export function useWorldClockForm(opts: UseWorldClockFormOptions) {
  const { t } = useI18n()
  const message = useMessage()
  const { confirm } = useConfirmDialog()

  const modalOpen = ref(false)
  const editing = ref<ClockCity | null>(null)
  const formRef = ref()
  const form = ref({ name: '', timezone: '', lat: null as number | null, lon: null as number | null })
  const geocoding = ref(false)

  const tzOptions = computed<SelectOption[]>(() =>
    COMMON_TZ.map(tz => ({ label: tz, value: tz })),
  )

  const rules = computed(() => ({
    name: [{ required: true, message: t('admin.worldClock.nameRequired'), trigger: 'blur' }],
    timezone: [
      { required: true, message: t('admin.worldClock.tzRequired'), trigger: 'blur' },
      {
        validator: (_r: unknown, value: string) => opts.isValidTimezone(value),
        message: t('admin.worldClock.tzInvalid'),
        trigger: 'blur',
      },
    ],
  }))

  const previewTime = computed(() => {
    if (!form.value.timezone || !opts.isValidTimezone(form.value.timezone)) return '—'
    try {
      return new Intl.DateTimeFormat('ru-RU', {
        timeZone: form.value.timezone,
        hour: '2-digit', minute: '2-digit', weekday: 'short',
        hourCycle: 'h23',
      }).format(opts.now.value)
    } catch {
      return '—'
    }
  })

  function openAdd() {
    editing.value = null
    form.value = { name: '', timezone: '', lat: null, lon: null }
    modalOpen.value = true
  }

  function openEdit(row: ClockCity) {
    editing.value = row
    form.value = {
      name: row.name,
      timezone: row.timezone,
      lat: row.lat ?? null,
      lon: row.lon ?? null,
    }
    modalOpen.value = true
  }

  async function onGeocode() {
    const q = form.value.name.trim()
    if (!q) return
    geocoding.value = true
    try {
      const url = `https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(q)}&count=1&language=ru&format=json`
      const res = await fetch(url)
      if (!res.ok) throw new Error('geocoding failed')
      const data = await res.json()
      const first = data?.results?.[0]
      if (!first) {
        message.warning(t('admin.worldClock.geocodeNotFound'))
        return
      }
      form.value.lat = Number(first.latitude)
      form.value.lon = Number(first.longitude)
      if (!form.value.timezone && first.timezone) {
        form.value.timezone = String(first.timezone)
      }
      message.success(t('admin.worldClock.geocodeOk'))
    } catch {
      message.error(t('admin.worldClock.geocodeError'))
    } finally {
      geocoding.value = false
    }
  }

  async function submit() {
    try {
      await formRef.value?.validate()
    } catch {
      return
    }
    const payload = {
      name: form.value.name.trim(),
      code: editing.value?.code ?? form.value.name.trim().slice(0, 3).toUpperCase(),
      timezone: form.value.timezone.trim(),
      lat: form.value.lat ?? undefined,
      lon: form.value.lon ?? undefined,
    }
    if (editing.value) {
      opts.update(editing.value.id, payload)
      message.success(t('admin.worldClock.saved'))
    } else {
      opts.add(payload)
      message.success(t('admin.worldClock.added'))
    }
    modalOpen.value = false
    nextTick(() => opts.onAfterMutation())
  }

  async function onDelete(row: ClockCity) {
    const ok = await confirm({
      title: t('admin.worldClock.confirmDelete', { name: row.name }),
      content: '',
      positiveText: t('common.delete'),
      negativeText: t('common.cancel'),
    })
    if (!ok) return
    opts.remove(row.id)
    message.success(t('admin.worldClock.deleted'))
    nextTick(() => opts.onAfterMutation())
  }

  async function onReset() {
    const ok = await confirm({
      title: t('admin.worldClock.confirmReset'),
      content: t('admin.worldClock.confirmResetHint'),
      positiveText: t('admin.worldClock.reset'),
      negativeText: t('common.cancel'),
    })
    if (!ok) return
    opts.reset()
    message.success(t('admin.worldClock.resetDone'))
    nextTick(() => opts.onAfterMutation())
  }

  return {
    modalOpen, editing, formRef, form, geocoding,
    tzOptions, rules, previewTime,
    openAdd, openEdit, onGeocode, submit, onDelete, onReset,
  }
}
