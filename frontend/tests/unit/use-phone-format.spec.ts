import { describe, it, expect, beforeEach, vi } from 'vitest'
import { ref } from 'vue'

const settingsDataRef = ref<any>(null)

vi.mock('../../src/queries/users', () => ({
  useStaffSettingsQuery: () => ({ data: settingsDataRef }),
}))

import { usePhoneFormat } from '../../src/composables/usePhoneFormat'

describe('usePhoneFormat (src/composables)', () => {
  beforeEach(() => {
    settingsDataRef.value = null
  })

  it('formatPhone returns empty string for null/undefined/empty', () => {
    const { formatPhone } = usePhoneFormat()
    expect(formatPhone(null)).toBe('')
    expect(formatPhone(undefined)).toBe('')
    expect(formatPhone('')).toBe('')
  })

  it('formatPhone returns phone unchanged when settings have no regex', () => {
    settingsDataRef.value = {}
    const { formatPhone } = usePhoneFormat()
    expect(formatPhone('+7 123 456')).toBe('+7 123 456')
  })

  it('formatPhone returns phone unchanged when regex pattern is empty', () => {
    settingsDataRef.value = { phone_extract_regex: '' }
    const { formatPhone } = usePhoneFormat()
    expect(formatPhone('+7 123 456')).toBe('+7 123 456')
  })

  it('formatPhone applies a capturing-group regex, preferring capture group 1', () => {
    settingsDataRef.value = { phone_extract_regex: '.*(\\+7 \\d{3} \\d{3}).*' }
    const { formatPhone } = usePhoneFormat()
    expect(formatPhone('Tel: +7 123 456 ext')).toBe('+7 123 456')
  })

  it('formatPhone falls back to m[0] when capture group 1 is missing', () => {
    settingsDataRef.value = { phone_extract_regex: '\\d{3}' }
    const { formatPhone } = usePhoneFormat()
    expect(formatPhone('abc 123 def')).toBe('123')
  })

  it('formatPhone returns phone unchanged when regex does not match', () => {
    settingsDataRef.value = { phone_extract_regex: '^(?:no-match)$' }
    const { formatPhone } = usePhoneFormat()
    expect(formatPhone('+7 123 456')).toBe('+7 123 456')
  })

  it('formatPhone swallows invalid-regex errors and returns the original', () => {
    settingsDataRef.value = { phone_extract_regex: '[' }
    const { formatPhone } = usePhoneFormat()
    expect(formatPhone('+7 123 456')).toBe('+7 123 456')
  })
})
