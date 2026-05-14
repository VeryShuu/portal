import { onBeforeUnmount } from 'vue'

export interface DebouncedFn<TArgs extends unknown[]> {
  (...args: TArgs): void
  cancel: () => void
  flush: () => void
}

export function useDebounceFn<TArgs extends unknown[]>(
  fn: (...args: TArgs) => void | Promise<void>,
  delay: number,
): DebouncedFn<TArgs> {
  let handle: ReturnType<typeof setTimeout> | null = null
  let pendingArgs: TArgs | null = null

  function cancel(): void {
    if (handle !== null) {
      clearTimeout(handle)
      handle = null
    }
    pendingArgs = null
  }

  function flush(): void {
    if (handle !== null && pendingArgs !== null) {
      clearTimeout(handle)
      const args = pendingArgs
      handle = null
      pendingArgs = null
      void fn(...args)
    }
  }

  const debounced = ((...args: TArgs) => {
    pendingArgs = args
    if (handle !== null) clearTimeout(handle)
    handle = setTimeout(() => {
      handle = null
      const a = pendingArgs as TArgs
      pendingArgs = null
      void fn(...a)
    }, delay)
  }) as DebouncedFn<TArgs>

  debounced.cancel = cancel
  debounced.flush = flush

  onBeforeUnmount(cancel)

  return debounced
}
