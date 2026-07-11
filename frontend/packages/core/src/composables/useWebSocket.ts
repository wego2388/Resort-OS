import { ref, onUnmounted } from 'vue'

export function useResortWebSocket(url: string) {
  const isConnected = ref(false)
  const status = ref<'connecting' | 'connected' | 'disconnected' | 'error'>('connecting')
  let ws: WebSocket | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let reconnectDelay = 1000
  // ⚠️ باج حقيقي كان هنا: onUnmounted كان بيعمل ws.close() بس من غير أي flag
  // — ws.onclose بيتنفّذ (async) حتى بعد close() المقصود، وكان بيجدول
  // reconnect تاني زي أي انقطاع حقيقي. يعني كل مرة الكاشير/الشيف يسيب شاشة
  // الـ KDS (يتنقّل لصفحة تانية)، اتصال WebSocket "زومبي" كان فضل يحاول
  // يعيد الاتصال للأبد من غير ما حد يقدر يوقفه (مفيش reference للـ component
  // عشان يلغيه)، ويعمل اتصال جديد فعلي كل مرة الشاشة تتفتح تاني من غير ما
  // القديم يتنضّف. اتصلح بـ flag `intentionalClose` بيمنع الـ reconnect لو
  // الإغلاق كان مقصود (unmount).
  let intentionalClose = false
  const handlers = ref<((data: unknown) => void)[]>([])

  function connect() {
    if (ws?.readyState === WebSocket.OPEN) return
    intentionalClose = false
    // كل WebSocket endpoint في الباك إند بقى بيتطلب ?token= JWT صالح
    // (wagdy.md A-01 — كانت الاتصالات دي كلها من غير أي تحقق هوية خالص).
    // نفس التوكن المستخدم في Authorization header للـ REST calls العادية.
    const token = localStorage.getItem('access_token')
    const authedUrl = token
      ? `${url}${url.includes('?') ? '&' : '?'}token=${encodeURIComponent(token)}`
      : url
    ws = new WebSocket(authedUrl)
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
      if (intentionalClose) return
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
    intentionalClose = true
    if (reconnectTimer) clearTimeout(reconnectTimer)
    ws?.close()
  })

  connect()
  return { isConnected, status, onMessage, send }
}
