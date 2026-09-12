import { useDialog } from 'naive-ui'

export interface ConfirmOptions {
  title: string
  content: string
  positiveText?: string
  negativeText?: string
  type?: 'warning' | 'error' | 'info' | 'success'
}

export function useConfirmDialog() {
  const dialog = useDialog()

  function confirm(options: ConfirmOptions): Promise<boolean> {
    return new Promise((resolve) => {
      dialog[options.type ?? 'warning']({
        title: options.title,
        content: options.content,
        positiveText: options.positiveText,
        negativeText: options.negativeText,
        onPositiveClick: () => resolve(true),
        onNegativeClick: () => resolve(false),
        onClose: () => resolve(false),
      })
    })
  }

  return { confirm }
}
