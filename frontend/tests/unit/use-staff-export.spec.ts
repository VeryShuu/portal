import { describe, it, expect, beforeEach, vi } from 'vitest'
import { ref } from 'vue'

const buildUrlMock = vi.fn()
const locationAssignMock = vi.fn()

vi.mock('../../src/api/users', () => ({
  buildUsersExportUrl: (...args: unknown[]) => buildUrlMock(...args),
}))

import { useStaffExport } from '../../src/composables/useStaffExport'

describe('useStaffExport (src/composables)', () => {
  beforeEach(() => {
    buildUrlMock.mockClear()
    locationAssignMock.mockClear()
    buildUrlMock.mockImplementation((p: any) => `url:${JSON.stringify(p)}`)
    vi.stubGlobal('location', { assign: locationAssignMock })
  })

  it('onExport filters falsy q/department/office and assigns the URL with sort=staff_custom', () => {
    const { onExport } = useStaffExport({
      q: ref(''),
      department: ref(null),
      office: ref(undefined as any),
    })
    onExport()

    expect(buildUrlMock).toHaveBeenCalledWith({
      q: undefined,
      department: undefined,
      office: undefined,
      sort: 'staff_custom',
    })
    expect(locationAssignMock).toHaveBeenCalledWith('url:{"sort":"staff_custom"}')
  })

  it('onExport passes through truthy values for q/department/office', () => {
    const { onExport } = useStaffExport({
      q: ref('alice'),
      department: ref('Sales'),
      office: ref('HQ'),
    })
    onExport()

    expect(buildUrlMock).toHaveBeenCalledWith({
      q: 'alice',
      department: 'Sales',
      office: 'HQ',
      sort: 'staff_custom',
    })
  })

  it('onPrint builds URL with format=xlsx and sort=staff_custom', () => {
    const { onPrint } = useStaffExport({
      q: ref(''),
      department: ref('Sales'),
      office: ref(''),
    })
    onPrint()

    expect(buildUrlMock).toHaveBeenCalledWith({
      q: undefined,
      department: 'Sales',
      office: undefined,
      sort: 'staff_custom',
      format: 'xlsx',
    })
    expect(locationAssignMock).toHaveBeenCalled()
  })
})
