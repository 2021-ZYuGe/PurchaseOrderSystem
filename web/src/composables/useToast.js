import { ref } from 'vue'

const toasts = ref([])
let seq = 0

export function useToast() {
  function remove(id) {
    toasts.value = toasts.value.filter((t) => t.id !== id)
  }

  function notify(message, type = 'info', duration = 4200) {
    const text = String(message || '').trim()
    if (!text) return
    const id = ++seq
    toasts.value.push({ id, message: text, type })
    window.setTimeout(() => remove(id), duration)
  }

  return {
    toasts,
    notify,
    remove,
    success: (message) => notify(message, 'success'),
    error: (message) => notify(message, 'error', 6000),
  }
}
