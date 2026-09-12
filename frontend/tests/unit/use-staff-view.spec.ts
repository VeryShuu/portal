import { describe, it, expect, beforeEach, vi } from 'vitest'

const isMobileRef = { value: false }

vi.mock('../../src/composables/useBreakpoints', () => ({
  useBreakpoints: () => ({ isMobile: isMobileRef }),
}))

import { useStaffView } from '../../src/composables/useStaffView'

describe('useStaffView (src/composables)', () => {
  beforeEach(() => {
    isMobileRef.value = false
    localStorage.clear()
  })

  it('defaults to table view when localStorage is empty', () => {
    const { view, effectiveView } = useStaffView()
    expect(view.value).toBe('table')
    expect(effectiveView.value).toBe('table')
  })

  it('reads the stored grid view from localStorage when valid', () => {
    localStorage.setItem('staff:view', 'grid')
    const { view, effectiveView } = useStaffView()
    expect(view.value).toBe('grid')
    expect(effectiveView.value).toBe('grid')
  })

  it('falls back to table view when stored value is invalid', () => {
    localStorage.setItem('staff:view', 'weird')
    const { view } = useStaffView()
    expect(view.value).toBe('table')
  })

  it('falls back to table view when localStorage.getItem throws', () => {
    const spy = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('denied')
    })
    const { view } = useStaffView()
    expect(view.value).toBe('table')
    spy.mockRestore()
  })

  it('effectiveView is forced to grid on mobile regardless of stored view', () => {
    localStorage.setItem('staff:view', 'table')
    isMobileRef.value = true
    const { view, effectiveView } = useStaffView()
    expect(view.value).toBe('table')
    expect(effectiveView.value).toBe('grid')
  })

  it('setView updates view and persists to localStorage', () => {
    const { view, setView } = useStaffView()
    setView('grid')
    expect(view.value).toBe('grid')
    expect(localStorage.getItem('staff:view')).toBe('grid')
  })

  it('setView swallows localStorage.setItem errors', () => {
    const spy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('denied')
    })
    const { view, setView } = useStaffView()
    expect(() => setView('grid')).not.toThrow()
    expect(view.value).toBe('grid')
    spy.mockRestore()
  })
})
