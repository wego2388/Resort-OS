import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api, setApiToken, registerAuthClearHandler } from '../api/client'
import { ENDPOINTS } from '../api/endpoints'
import type { User } from '../types'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  // T-01: access_token في memory فقط (مش localStorage) — يتجدّد من httpOnly
  // cookie عبر /auth/refresh عند كل reload. المهاجمة بـ XSS تقدر تسرق
  // localStorage بس مش httpOnly cookie.
  const token = ref<string | null>(null)
  const isLoading = ref(false)

  // client.ts's 401→refresh-fails path calls this to clear our state without
  // importing this store back (that would be circular — see client.ts).
  registerAuthClearHandler(() => {
    user.value = null
    token.value = null
  })

  const isAuthenticated = computed(() => !!token.value && !!user.value)
  const role = computed(() => user.value?.role ?? '')
  const branchId = computed(() => user.value?.branch_id ?? 1)

  // Mirrors backend ROLE_LEVELS (app/core/deps.py)
  const ROLE_LEVELS: Record<string, number> = {
    super_admin: 100,
    admin: 80,
    accountant: 70,
    hr_manager: 70,
    manager: 60,
    supervisor: 50,
    receptionist: 40,
    cashier: 40,
    waiter: 30,
    chef: 30,
    kitchen: 30,
    employee: 20,
    customer: 0,
    guest: 0,
  }

  function hasRole(minRole: string): boolean {
    const userLevel = ROLE_LEVELS[role.value] ?? 0
    const minLevel = ROLE_LEVELS[minRole] ?? 0
    return userLevel >= minLevel
  }

  const roleLevel = computed(() => ROLE_LEVELS[role.value] ?? 0)

  // Mirrors backend app/core/deps.py::MANDATORY_2FA_ROLES
  const MANDATORY_2FA_ROLES = new Set(['super_admin', 'accountant'])

  const needsTwoFactorSetup = computed(
    () => !!user.value && MANDATORY_2FA_ROLES.has(role.value) && !user.value.two_factor_enabled,
  )

  // ── helpers ─────────────────────────────────────────────────────────────

  // نقطة واحدة لتغيير الـ token — يحدّث Pinia + axios.defaults في نفس الوقت
  // عشان كل request تاني (REST + WebSocket) يلاقي الـ token جاهز فوراً.
  function _setToken(t: string | null) {
    token.value = t
    setApiToken(t)
  }

  async function fetchUser() {
    if (!token.value) return
    const res = await api.get(ENDPOINTS.auth.me)
    user.value = res.data
  }

  // ── Public actions ───────────────────────────────────────────────────────

  async function login(username: string, password: string, otpCode?: string) {
    isLoading.value = true
    try {
      const form = new URLSearchParams()
      form.append('username', username.trim())
      form.append('password', password.trim())
      if (otpCode) form.append('otp_code', otpCode.trim())
      const res = await api.post(ENDPOINTS.auth.login, form, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        withCredentials: true,
      })
      _setToken(res.data.access_token)
      await fetchUser()
    } finally {
      isLoading.value = false
    }
  }

  // T-01: يُستدعى عند app init (main.ts) — يجدّد access_token من httpOnly cookie.
  // لو ما فيش cookie صالح يرجع false والـ router guard بيودّي /login.
  async function initAuth(): Promise<boolean> {
    try {
      const res = await api.post(ENDPOINTS.auth.refresh, {}, { withCredentials: true })
      _setToken(res.data.access_token)
      await fetchUser()
      return true
    } catch {
      _setToken(null)
      user.value = null
      return false
    }
  }

  // تبديل هوية المشغّل على جهاز كاشير (pin switch)
  async function pinSwitch(targetUserId: number, pin: string) {
    isLoading.value = true
    try {
      const res = await api.post(ENDPOINTS.core.pinSwitch, { user_id: targetUserId, pin })
      _setToken(res.data.access_token)
      user.value = res.data.user
    } finally {
      isLoading.value = false
    }
  }

  function logout() {
    // نبلّغ الـ backend يمسح الـ refresh_token cookie — fire and forget
    api.post(ENDPOINTS.auth.logout, { token: token.value ?? '' }, { withCredentials: true }).catch(() => {})
    _setToken(null)
    user.value = null
    window.location.replace('/login')
  }

  return {
    user, token, isAuthenticated, role, branchId, isLoading,
    login, logout, fetchUser, initAuth, hasRole, roleLevel,
    needsTwoFactorSetup, pinSwitch,
  }
})
