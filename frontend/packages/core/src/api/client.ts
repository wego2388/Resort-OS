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
let _clearAuthHandler: (() => void) | null = null
export function registerAuthClearHandler(fn: () => void) {
  _clearAuthHandler = fn
}

// ── Silent token refresh ──────────────────────────────────────────────────
// لو access_token انتهت صلاحيته أثناء الاستخدام (30 دقيقة)، نجدده من
// httpOnly cookie مرة واحدة ثم نعيد الـ request. لو فشل → /login.
//
// _isRefreshing: يمنع parallel refresh (لو 3 requests فشلوا بـ 401 في نفس
// الوقت، نعمل refresh واحدة بس). _queue: الـ requests المنتظرة تتحل بعده.

let _isRefreshing = false
let _queue: Array<{ resolve: (token: string) => void; reject: (err: unknown) => void }> = []

function _processQueue(err: unknown, token: string | null) {
  _queue.forEach((p) => (err ? p.reject(err) : p.resolve(token!)))
  _queue = []
}

function _clearAuthAndRedirect() {
  setApiToken(null)
  _clearAuthHandler?.()
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
      if (_isRefreshing) {
        return new Promise((resolve, reject) => {
          _queue.push({
            resolve: (newToken) => {
              err.config.headers.Authorization = `Bearer ${newToken}`
              resolve(api(err.config))
            },
            reject,
          })
        })
      }

      _isRefreshing = true
      err.config._retried = true

      try {
        const res = await api.post(ENDPOINTS.auth.refresh, {}, { withCredentials: true })
        const newToken: string = res.data.access_token
        setApiToken(newToken)
        _processQueue(null, newToken)
        err.config.headers.Authorization = `Bearer ${newToken}`
        return api(err.config)
      } catch (refreshErr) {
        _processQueue(refreshErr, null)
        _clearAuthAndRedirect()
        return Promise.reject(refreshErr)
      } finally {
        _isRefreshing = false
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
