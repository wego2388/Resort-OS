import axios from 'axios'
import { ENDPOINTS } from './endpoints'

export const api = axios.create({
  baseURL: '',  // Vite proxy handles /api → localhost:8005
  headers: { 'Content-Type': 'application/json' },
  timeout: 30_000,
  withCredentials: true,  // T-01: يسمح للـ browser يبعت/يستقبل httpOnly cookie مع كل request
})

// ── Token management ──────────────────────────────────────────────────────
// الـ token يتحفظ هنا في module scope — مش في Pinia (لتفادي circular dependency)
// ومش في localStorage (T-01 security). useAuthStore بيستدعي setApiToken()
// كل ما يتغيّر الـ token (login / refresh / logout).
let _token: string | null = null

export function setApiToken(token: string | null) {
  _token = token
  if (token) {
    api.defaults.headers.common['Authorization'] = `Bearer ${token}`
  } else {
    delete api.defaults.headers.common['Authorization']
  }
}

export function getApiToken(): string | null {
  return _token
}

// useAuthStore (stores/auth.ts) imports this module for setApiToken(), so this
// module can't import the store back without a circular import — it registers
// a clear-handler here instead, once, right after the store is first created
// in main.ts (always before any request can 401).
let _clearAuthHandler: (() => void | Promise<void>) | null = null
export function registerAuthClearHandler(fn: () => void | Promise<void>) {
  _clearAuthHandler = fn
}

// ── Silent token refresh ──────────────────────────────────────────────────
// لو access_token انتهت صلاحيته أثناء الاستخدام (30 دقيقة)، نجدده من
// httpOnly cookie مرة واحدة ثم نعيد الـ request. لو فشل → /login.
//
// A module-scoped promise deduplicates requests inside one tab. Web Locks (or
// the bounded localStorage lease fallback) serializes refresh-cookie rotation
// across tabs as well: the cookie is shared, and concurrent rotations used to
// look like token replay and revoke the whole session family.
let _refreshPromise: Promise<string> | null = null
const REFRESH_LOCK_NAME = 'resort-os:refresh-cookie-rotation'
const REFRESH_LEASE_KEY = 'resort-os:refresh-cookie-lease'
const REFRESH_LEASE_MS = 35_000

function wait(ms: number): Promise<void> {
  return new Promise(resolve => window.setTimeout(resolve, ms))
}

async function withStorageLease<T>(operation: () => Promise<T>): Promise<T> {
  const owner = globalThis.crypto?.randomUUID?.()
    ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`
  const deadline = Date.now() + REFRESH_LEASE_MS

  try {
    while (Date.now() < deadline) {
      const now = Date.now()
      let current: { owner?: string; expiresAt?: number } = {}
      try {
        current = JSON.parse(localStorage.getItem(REFRESH_LEASE_KEY) ?? '{}')
      } catch { /* expired/corrupt lease is replaceable */ }

      if (!current.owner || (current.expiresAt ?? 0) <= now) {
        localStorage.setItem(REFRESH_LEASE_KEY, JSON.stringify({
          owner,
          expiresAt: now + REFRESH_LEASE_MS,
        }))
        // Let a simultaneous contender finish its write, then confirm the
        // winner. This avoids both tabs believing they acquired the lease.
        await wait(45 + Math.floor(Math.random() * 35))
        const confirmed = JSON.parse(localStorage.getItem(REFRESH_LEASE_KEY) ?? '{}')
        if (confirmed.owner === owner) {
          try {
            return await operation()
          } finally {
            const latest = JSON.parse(localStorage.getItem(REFRESH_LEASE_KEY) ?? '{}')
            if (latest.owner === owner) localStorage.removeItem(REFRESH_LEASE_KEY)
          }
        }
      }
      await wait(80 + Math.floor(Math.random() * 70))
    }
  } catch {
    // Storage can be unavailable in privacy modes. The in-tab promise still
    // protects this page; execute rather than making login impossible.
    return operation()
  }
  throw new Error('Timed out waiting for the authentication refresh lock')
}

async function withCrossTabRefreshLock<T>(operation: () => Promise<T>): Promise<T> {
  if (typeof navigator !== 'undefined' && navigator.locks?.request) {
    return navigator.locks.request(REFRESH_LOCK_NAME, { mode: 'exclusive' }, operation)
  }
  return withStorageLease(operation)
}

export function refreshAccessToken(): Promise<string> {
  if (_refreshPromise) return _refreshPromise
  _refreshPromise = withCrossTabRefreshLock(async () => {
    const res = await api.post(ENDPOINTS.auth.refresh, {}, { withCredentials: true })
    const newToken: string = res.data.access_token
    setApiToken(newToken)
    return newToken
  }).finally(() => {
    _refreshPromise = null
  })
  return _refreshPromise
}

async function _clearAuthAndRedirect() {
  setApiToken(null)
  await _clearAuthHandler?.()
  window.location.href = '/login'
}

api.interceptors.response.use(
  (res) => res,
  async (err) => {
    const url: string = err.config?.url ?? ''
    const status: number = err.response?.status

    // Auth endpoints لازم يتعاملوا معاهم المستدعي نفسه — مش الـ interceptor.
    // لو interceptor يمسك 401 من /auth/refresh ويعمل redirect → infinite loop.
    const isAuthEndpoint = url.startsWith('/api/v1/auth/')

    // ── 401 على endpoint عادي: جرب silent refresh أولاً ─────────────────
    if (status === 401 && !isAuthEndpoint && !err.config?._retried) {
      err.config._retried = true

      try {
        const newToken = await refreshAccessToken()
        err.config.headers.Authorization = `Bearer ${newToken}`
        return api(err.config)
      } catch (refreshErr) {
        await _clearAuthAndRedirect()
        return Promise.reject(refreshErr)
      }
    }

    // ── 403 بـ 2FA_REQUIRED ───────────────────────────────────────────────
    if (status === 403 && err.response?.data?.detail?.code === '2FA_REQUIRED') {
      if (window.location.pathname !== '/2fa-setup') {
        window.location.href = '/2fa-setup'
      }
    }

    if (status === 403 && err.response?.data?.detail?.code === 'PASSWORD_CHANGE_REQUIRED') {
      if (window.location.pathname !== '/change-temporary-password') {
        window.location.href = '/change-temporary-password'
      }
    }

    return Promise.reject(err)
  }
)
