import { ref, onBeforeUnmount, type Ref } from 'vue'

export interface UseIntervalReturn {
  isActive: Ref<boolean>
  start: (delayOverride?: number) => void
  stop: () => void
  restart: (delayOverride?: number) => void
}

export function useInterval(
  callback: () => void | Promise<void>,
  delay: number,
  options: { immediate?: boolean } = {},
): UseIntervalReturn {
  const isActive = ref(false)
  let handle: ReturnType<typeof setInterval> | null = null
  let currentDelay = delay

  function stop(): void {
    if (handle !== null) {
      clearInterval(handle)
      handle = null
    }
    isActive.value = false
  }

  function start(delayOverride?: number): void {
    stop()
    if (typeof delayOverride === 'number') currentDelay = delayOverride
    handle = setInterval(() => { void callback() }, currentDelay)
    isActive.value = true
  }

  function restart(delayOverride?: number): void {
    start(delayOverride)
  }

  if (options.immediate) start()

  onBeforeUnmount(stop)

  return { isActive, start, stop, restart }
}
