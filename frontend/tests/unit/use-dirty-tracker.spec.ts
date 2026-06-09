import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useDirtyTracker } from '../../src/composables/useDirtyTracker'

describe('useDirtyTracker', () => {
  it('is not dirty before the first markPristine (empty baseline)', () => {
    const state = ref('a')
    const { isDirty } = useDirtyTracker(() => state.value)
    expect(isDirty.value).toBe(false)
  })

  it('is not dirty right after markPristine', () => {
    const state = ref('a')
    const { isDirty, markPristine } = useDirtyTracker(() => state.value)
    markPristine()
    expect(isDirty.value).toBe(false)
  })

  it('becomes dirty when the snapshot changes after markPristine', () => {
    const state = ref('a')
    const { isDirty, markPristine } = useDirtyTracker(() => state.value)
    markPristine()
    state.value = 'b'
    expect(isDirty.value).toBe(true)
  })

  it('returns to pristine after re-baselining', () => {
    const state = ref('a')
    const { isDirty, markPristine } = useDirtyTracker(() => state.value)
    markPristine()
    state.value = 'b'
    expect(isDirty.value).toBe(true)
    markPristine()
    expect(isDirty.value).toBe(false)
  })

  it('is not dirty when the value reverts to the baseline value', () => {
    const state = ref('a')
    const { isDirty, markPristine } = useDirtyTracker(() => state.value)
    markPristine()
    state.value = 'b'
    state.value = 'a'
    expect(isDirty.value).toBe(false)
  })
})
