import axios from 'axios'
import { ENDPOINTS } from './endpoints'

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
    // ⚠️ باج حقيقي كان هنا: POST /auth/login نفسه بيرجّع 401 على باسورد غلط
    // أو (بعد تفعيل LOGIN_2FA_ENFORCED) كود 2FA ناقص/غلط — أي واحدة فيهم
    // كانت بتفعّل الشرط تحت وتعمل window.location.href='/login' فوري، يعني
    // LoginView.vue's catch block عمره ما كان هيلحق يعرض حقل كود الـ 2FA
    // (الصفحة بتتحمّل من جديد قبل ما الـ state يتحدّث). الشرط الأصلي مقصود
    // بس لطلبات authenticated بعد ما كان فيه توكن صالح وبقى منتهي/مرفوض —
    // مش لمحاولة تسجيل الدخول نفسها (اللي أصلاً معندهاش توكن نتخلص منه).
    const isLoginRequest = err.config?.url === ENDPOINTS.auth.login
    if (err.response?.status === 401 && !isLoginRequest) {
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
