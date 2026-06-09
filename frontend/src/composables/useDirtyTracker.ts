import { computed, ref, type ComputedRef } from 'vue'

export interface DirtyTracker {
  isDirty: ComputedRef<boolean>
  markPristine: () => void
}

export function useDirtyTracker(snapshot: () => string): DirtyTracker {
  const baseline = ref('')

  function markPristine() {
    baseline.value = snapshot()
  }

  const isDirty = computed(() => baseline.value !== '' && snapshot() !== baseline.value)

  return { isDirty, markPristine }
}
