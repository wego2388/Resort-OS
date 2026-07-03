import axios from 'axios'

export const api = axios.create({
  baseURL: '',  // Vite proxy handles /api → localhost:8005
  headers: { 'Content-Type': 'application/json' },
  timeout: 30_000,
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (res) => res,
  async (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('access_token')
      window.location.href = '/login'
    }
    // Defense-in-depth: the router's `beforeEach` guard already redirects
    // super_admin/accountant to /2fa-setup proactively (via
    // useAuthStore.needsTwoFactorSetup) once GET /auth/me comes back with
    // two_factor_enabled=false. This catches it here too in case that state
    // is ever stale (e.g. a second mandatory-2FA role added server-side
    // before the frontend's role list is updated) — without this, every
    // other screen just silently swallowed the 403 and rendered empty data.
    if (err.response?.status === 403 && err.response?.data?.detail?.code === '2FA_REQUIRED') {
      if (window.location.pathname !== '/2fa-setup') {
        window.location.href = '/2fa-setup'
      }
    }
    return Promise.reject(err)
  }
)
