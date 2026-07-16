import { ref, onUnmounted } from 'vue'
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

export function useResortWebSocket(pathOrUrl: string) {
  const isConnected = ref(false)
  const status = ref<'connecting' | 'connected' | 'disconnected' | 'error'>('connecting')
  let ws: WebSocket | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let reconnectDelay = 1000
  // ⚠️ باج حقيقي: onUnmounted من غير flag كان بيجدول reconnect بعد close()
  // المقصود — اتصلح بـ intentionalClose.
  let intentionalClose = false
  const handlers = ref<((data: unknown) => void)[]>([])

  function connect() {
    if (ws?.readyState === WebSocket.OPEN) return
    intentionalClose = false

    // T-01: access_token في module scope جوه api/client.ts (مش localStorage)
    const token = getApiToken()
    const baseUrl = _toWsUrl(pathOrUrl)
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
      } catch { /* ignore malformed */ }
    }

    ws.onclose = () => {
      isConnected.value = false
      status.value = 'disconnected'
      if (intentionalClose) return
      // لو مفيش token (الـ session انتهت أو user عمل logout) — وقّف الـ reconnect.
      // ده بيمنع طوفان 403 في الـ logs لما refresh token يفشل ويتعمل logout.
      if (!getApiToken()) return
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
