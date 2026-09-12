import type { Ref } from 'vue'
import { buildUsersExportUrl } from '../api/users'

export interface UseStaffExportOptions {
  q: Ref<string | undefined>
  department: Ref<string | null>
  office: Ref<string | null>
}

export function useStaffExport(options: UseStaffExportOptions) {
  function onExport() {
    const url = buildUsersExportUrl({
      q: options.q.value || undefined,
      department: options.department.value || undefined,
      office: options.office.value || undefined,
      sort: 'staff_custom',
    })
    window.location.assign(url)
  }

  function onPrint() {
    const url = buildUsersExportUrl({
      q: options.q.value || undefined,
      department: options.department.value || undefined,
      office: options.office.value || undefined,
      sort: 'staff_custom',
      format: 'xlsx',
    })
    window.location.assign(url)
  }

  return { onExport, onPrint }
}
