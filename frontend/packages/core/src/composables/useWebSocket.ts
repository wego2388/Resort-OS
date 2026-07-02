import { ref, onUnmounted } from 'vue'

export function useResortWebSocket(url: string) {
  const isConnected = ref(false)
  const status = ref<'connecting' | 'connected' | 'disconnected' | 'error'>('connecting')
  let ws: WebSocket | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let reconnectDelay = 1000
  const handlers = ref<((data: unknown) => void)[]>([])

  function connect() {
    if (ws?.readyState === WebSocket.OPEN) return
    ws = new WebSocket(url)
    status.value = 'connecting'

    ws.onopen = () => {
      isConnected.value = true
      status.value = 'connected'
      reconnectDelay = 1000
    }

    ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data)
        if (data.type === 'pong') return
        handlers.value.forEach(h => h(data))
      } catch { /* ignore */ }
    }

    ws.onclose = () => {
      isConnected.value = false
      status.value = 'disconnected'
      reconnectTimer = setTimeout(() => {
        reconnectDelay = Math.min(reconnectDelay * 2, 30_000)
        connect()
      }, reconnectDelay)
    }

    ws.onerror = () => { status.value = 'error' }
  }

  function onMessage(handler: (data: unknown) => void) {
    handlers.value.push(handler)
  }

  function send(data: unknown) {
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(data))
    }
  }

  onUnmounted(() => {
    if (reconnectTimer) clearTimeout(reconnectTimer)
    ws?.close()
  })

  connect()
  return { isConnected, status, onMessage, send }
}
