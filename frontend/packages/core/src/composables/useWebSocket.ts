import { ref, watch, onUnmounted, type MaybeRefOrGetter, toValue } from 'vue'
import { getApiToken } from '../api/client'

/**
 * يحوّل relative path (/api/v1/...) لـ WebSocket URL كامل.
 * لو اتبعتله URL كامل (يبدأ بـ ws:// أو wss://) بيرجعه زي ما هو.
 *
 * ليه relative ومش absolute؟
 * - في dev: الـ vite proxy (ws: true) بيعمل forward تلقائياً لأي WS على /api/
 * - في production (nginx): نفس الشيء — reverse proxy بيمسك /api/v1/ws/*
 * - بكده مفيش hardcoded host/port في الفرونت إند
 */
function _toWsUrl(pathOrUrl: string): string {
  if (pathOrUrl.startsWith('ws://') || pathOrUrl.startsWith('wss://')) {
    return pathOrUrl
  }
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}${pathOrUrl}`
}

/**
 * useResortWebSocket — composable للـ WebSocket مع reconnect تلقائي.
 *
 * يقبل pathOrUrl كـ string ثابت أو Ref أو getter (MaybeRefOrGetter):
 * - لو القيمة null/undefined/'': لا يفتح اتصال — يغلق الموجود لو كان مفتوحاً.
 * - لما تتغير القيمة: يغلق الاتصال القديم ويفتح جديد تلقائياً.
 *
 * ده يحل مشكلة branchId=null في GuestAlertsBell: الـ composable كان بيتنفذ
 * مرة واحدة في setup بـ alertsWs(0) (لأن branchId ?? 0 = 0 لما null) ويحرق
 * 4 اتصالات فاشلة في الكونسول قبل ما الـ bootstrap يكتمل.
 */
export function useResortWebSocket(pathOrUrl: MaybeRefOrGetter<string | null | undefined>) {
  const isConnected = ref(false)
  const status = ref<'connecting' | 'connected' | 'disconnected' | 'error'>('disconnected')
  let ws: WebSocket | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let reconnectDelay = 1000
  // ⚠️ باج حقيقي: onUnmounted من غير flag كان بيجدول reconnect بعد close()
  // المقصود — اتصلح بـ intentionalClose.
  let intentionalClose = false
  const handlers = ref<((data: unknown) => void)[]>([])

  function _closeSocket() {
    intentionalClose = true
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    if (ws) {
      ws.onclose = null
      ws.onerror = null
      ws.onmessage = null
      ws.onopen = null
      ws.close()
      ws = null
    }
    isConnected.value = false
    status.value = 'disconnected'
  }

  function connect(url: string) {
    _closeSocket()
    intentionalClose = false
    reconnectDelay = 1000

    const token = getApiToken()
    const baseUrl = _toWsUrl(url)
    const authedUrl = token
      ? `${baseUrl}${baseUrl.includes('?') ? '&' : '?'}token=${encodeURIComponent(token)}`
      : baseUrl

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
      } catch { /* ignore malformed frames */ }
    }

    ws.onclose = () => {
      isConnected.value = false
      status.value = 'disconnected'
      if (intentionalClose) return
      // لو مفيش token (session انتهت أو logout) — وقّف الـ reconnect.
      // بيمنع طوفان 403 في الـ logs لما refresh token يفشل.
      if (!getApiToken()) return
      reconnectTimer = setTimeout(() => {
        reconnectDelay = Math.min(reconnectDelay * 2, 30_000)
        const current = toValue(pathOrUrl)
        if (current) connect(current)
      }, reconnectDelay)
    }

    ws.onerror = () => { status.value = 'error' }
  }

  // watch بيراقب التغيير في الـ URL (أو branchId) — لما يتغير من null لقيمة
  // حقيقية (بعد bootstrap) بيفتح الاتصال أوتوماتيكياً. لما يرجع null/''
  // بيغلق الاتصال القائم. immediate: true يطبّق الحالة الحالية فوراً.
  watch(
    () => toValue(pathOrUrl),
    (url) => {
      if (url) {
        connect(url)
      } else {
        _closeSocket()
      }
    },
    { immediate: true },
  )

  function onMessage(handler: (data: unknown) => void) {
    handlers.value.push(handler)
  }

  function send(data: unknown) {
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(data))
    }
  }

  onUnmounted(() => {
    _closeSocket()
  })

  return { isConnected, status, onMessage, send }
}
