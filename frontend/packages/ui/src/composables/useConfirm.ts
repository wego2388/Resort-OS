import { ref } from 'vue'

interface ConfirmOptions {
  title?: string
  message: string
  confirmText?: string
  cancelText?: string
  danger?: boolean
}

const isOpen = ref(false)
const options = ref<ConfirmOptions>({ message: '' })
let resolver: ((value: boolean) => void) | null = null

// Singleton state shared across the whole app — one <ConfirmDialogContainer />
// mounted once in App.vue (same pattern as useToast/ToastContainer), so any
// screen can call `const { confirm } = useConfirm(); if (await confirm(...))`
// instead of hand-rolling a native confirm()/alert() or its own modal.
export function useConfirm() {
  function confirm(opts: ConfirmOptions | string): Promise<boolean> {
    options.value = typeof opts === 'string' ? { message: opts } : opts
    isOpen.value = true
    return new Promise((resolve) => {
      resolver = resolve
    })
  }

  function handleConfirm() {
    isOpen.value = false
    resolver?.(true)
    resolver = null
  }

  function handleCancel() {
    isOpen.value = false
    resolver?.(false)
    resolver = null
  }

  return { isOpen, options, confirm, handleConfirm, handleCancel }
}
