import { ref } from 'vue'

interface Toast { id: number; message: string; type: 'success' | 'error' | 'warning' | 'info' }
const toasts = ref<Toast[]>([])
let nextId = 1

export function useToast() {
  function add(message: string, type: Toast['type'] = 'info', duration = 3000) {
    const id = nextId++
    toasts.value.push({ id, message, type })
    setTimeout(() => remove(id), duration)
  }

  function remove(id: number) {
    toasts.value = toasts.value.filter(t => t.id !== id)
  }

  return {
    toasts,
    remove,
    success: (m: string) => add(m, 'success'),
    error:   (m: string) => add(m, 'error'),
    warning: (m: string) => add(m, 'warning'),
    info:    (m: string) => add(m, 'info'),
  }
}
