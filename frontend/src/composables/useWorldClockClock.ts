import { onBeforeUnmount, onMounted, ref } from 'vue'

export function useWorldClockClock() {
  const now = ref(new Date())
  let timer: ReturnType<typeof setInterval> | null = null

  onMounted(() => {
    timer = setInterval(() => { now.value = new Date() }, 30_000)
  })

  onBeforeUnmount(() => {
    if (timer) clearInterval(timer)
  })

  function formatLocal(tz: string): string {
    try {
      return new Intl.DateTimeFormat('ru-RU', {
        timeZone: tz, hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
      }).format(now.value)
    } catch {
      return '—'
    }
  }

  return { now, formatLocal }
}
