import type { Ref } from 'vue'
import { useFormLeaveGuard } from './useFormLeaveGuard'

export interface UseStaffLeaveGuardOptions {
  editMode: Ref<boolean>
  dirty: Ref<boolean>
}

export function useStaffLeaveGuard(options: UseStaffLeaveGuardOptions) {
  useFormLeaveGuard({
    enabled: options.editMode,
    dirty: options.dirty,
    guardBeforeUnload: true,
    i18nKeys: {
      title: 'staff.edit.leaveTitle',
      content: 'staff.edit.leaveContent',
      confirm: 'staff.edit.leaveConfirm',
    },
  })
}
