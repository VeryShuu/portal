import type { Ref } from 'vue'
import { onBeforeUnmount, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useDialog } from 'naive-ui'
import { onBeforeRouteLeave } from 'vue-router'

export interface FormLeaveGuardI18nKeys {
  title: string
  content: string
  confirm: string
  cancel?: string
}

export interface UseFormLeaveGuardOptions {
  dirty: Readonly<Ref<boolean>>
  i18nKeys: FormLeaveGuardI18nKeys
  enabled?: Readonly<Ref<boolean>>
  guardBeforeUnload?: boolean
}

export function useFormLeaveGuard(options: UseFormLeaveGuardOptions) {
  const { dirty, i18nKeys, enabled, guardBeforeUnload = false } = options
  const { t } = useI18n()
  const dialog = useDialog()

  function isActive(): boolean {
    return (enabled?.value ?? true) && dirty.value
  }

  onBeforeRouteLeave(() => {
    if (!isActive()) return true
    return new Promise<boolean>((resolve) => {
      dialog.warning({
        title: t(i18nKeys.title),
        content: t(i18nKeys.content),
        positiveText: t(i18nKeys.confirm),
        negativeText: t(i18nKeys.cancel ?? 'common.cancel'),
        onPositiveClick: () => resolve(true),
        onNegativeClick: () => resolve(false),
        onClose: () => resolve(false),
        onMaskClick: () => resolve(false),
      })
    })
  })

  if (guardBeforeUnload) {
    const beforeUnloadHandler = (e: BeforeUnloadEvent) => {
      if (isActive()) {
        e.preventDefault()
        e.returnValue = ''
      }
    }
    onMounted(() => {
      window.addEventListener('beforeunload', beforeUnloadHandler)
    })
    onBeforeUnmount(() => {
      window.removeEventListener('beforeunload', beforeUnloadHandler)
    })
  }
}
