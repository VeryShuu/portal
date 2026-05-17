import type { Ref } from 'vue'
import { onBeforeUnmount, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useDialog } from 'naive-ui'
import { onBeforeRouteLeave } from 'vue-router'

export interface UseStaffLeaveGuardOptions {
  editMode: Ref<boolean>
  dirty: Ref<boolean>
}

export function useStaffLeaveGuard(options: UseStaffLeaveGuardOptions) {
  const { t } = useI18n()
  const dialog = useDialog()

  function beforeUnloadHandler(e: BeforeUnloadEvent) {
    if (options.editMode.value && options.dirty.value) {
      e.preventDefault()
      e.returnValue = ''
    }
  }

  onBeforeRouteLeave((_to, _from, next) => {
    if (!options.editMode.value || !options.dirty.value) {
      next()
      return
    }
    dialog.warning({
      title: t('staff.edit.leaveTitle'),
      content: t('staff.edit.leaveContent'),
      positiveText: t('staff.edit.leaveConfirm'),
      negativeText: t('common.cancel'),
      onPositiveClick: () => next(),
      onNegativeClick: () => next(false),
      onClose: () => next(false),
      onMaskClick: () => next(false),
    })
  })

  onMounted(() => {
    window.addEventListener('beforeunload', beforeUnloadHandler)
  })

  onBeforeUnmount(() => {
    window.removeEventListener('beforeunload', beforeUnloadHandler)
  })
}
