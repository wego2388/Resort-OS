import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api, setApiToken, registerAuthClearHandler } from '../api/client'
import { ENDPOINTS } from '../api/endpoints'
import type { User } from '../types'

type IdentityTransitionHandler = () => void | Promise<void>
let identityTransitionHandler: IdentityTransitionHandler | null = null

/**
 * Apps can register cleanup for browser state that must not cross an
 * authenticated identity boundary (for example legacy staff API caches).
 */
export function registerAuthIdentityTransitionHandler(handler: IdentityTransitionHandler): void {
  identityTransitionHandler = handler
}

async function clearIdentityBoundClientState(): Promise<void> {
  try {
    await identityTransitionHandler?.()
  } catch {
    // Cache/storage cleanup must be best-effort and may be unavailable in
    // private browsing. It must never keep a user signed in or block logout.
  }
}

// CX-02C — bootstrap response shape mirrors GET /api/v1/auth/bootstrap.
// contract_version=1 is the only stable version; callers must not assume
// the shape is stable without checking the version field.
export interface BootstrapData {
  contract_version: number
  user: User
  active_branch_id: number | null
  default_branch_id: number | null
  allowed_branch_ids: number[]
  requires_branch_selection: boolean
  effective_permissions: string[]
}

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  // T-01: access_token في memory فقط (مش localStorage) — يتجدّد من httpOnly
  // cookie عبر /auth/refresh عند كل reload. المهاجمة بـ XSS تقدر تسرق
  // localStorage بس مش httpOnly cookie.
  const token = ref<string | null>(null)
  // Short-lived bootstrap proof lives in memory only. Never persist it in
  // localStorage/sessionStorage: a copied development identity must still
  // require the out-of-band token on a new browser session.
  const pendingEnrollmentToken = ref('')
  const isLoading = ref(false)

  // CX-02C — session-scoped branch context. These are populated by
  // fetchBootstrap() immediately after login/initAuth. They are NEVER derived
  // from user.branch_id (which is a legacy Employee FK, not an auth source).
  //
  // activeBranchId:   the branch this refresh family is currently scoped to.
  //                   null means the session has no branch context yet
  //                   (requires_branch_selection=true on the bootstrap response).
  // allowedBranchIds: every branch this account holds an active membership in.
  //                   super_admin receives all active branches from the server.
  // effectivePermissions: server-evaluated permission set for activeBranchId.
  //                   Empty array = no branch context yet, all policy gates fail.
  const activeBranchId = ref<number | null>(null)
  const allowedBranchIds = ref<number[]>([])
  const effectivePermissions = ref<string[]>([])
  const requiresBranchSelection = ref(false)

  // client.ts's 401→refresh-fails path calls this to clear our state without
  // importing this store back (that would be circular — see client.ts).
  registerAuthClearHandler(async () => {
    await clearIdentityBoundClientState()
    user.value = null
    token.value = null
    pendingEnrollmentToken.value = ''
    activeBranchId.value = null
    allowedBranchIds.value = []
    effectivePermissions.value = []
    requiresBranchSelection.value = false
  })

  const isAuthenticated = computed(() => !!token.value && !!user.value)
  const role = computed(() => user.value?.role ?? '')

  // CX-02C: branchId is now the session-scoped activeBranchId from bootstrap.
  // There is NO fallback to 1. A null value means the session has no branch
  // context — callers must handle null explicitly and must not default to 1.
  // The old `user.branch_id ?? 1` pattern is prohibited (no live auth source).
  const branchId = computed(() => activeBranchId.value)

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
    timeshare_agent: 25,
    employee: 20,
    customer: 0,
    guest: 0,
  }

  function hasRole(minRole: string): boolean {
    const userLevel = ROLE_LEVELS[role.value]
    const minLevel = ROLE_LEVELS[minRole]
    // Unknown roles and misspelled requirements must fail closed. Treating an
    // unknown minimum as level 0 previously made every authenticated account
    // pass the frontend guard.
    if (userLevel == null || minLevel == null) return false
    return userLevel >= minLevel
  }

  // CX-02C — server-evaluated permission check.
  // effectivePermissions are scoped to the active branch from bootstrap.
  // Falls back to false (fail-closed) when no branch context exists.
  function hasPermission(permission: string): boolean {
    return effectivePermissions.value.includes(permission)
  }

  const roleLevel = computed(() => ROLE_LEVELS[role.value] ?? -1)

  // Mirrors backend app/core/deps.py::MANDATORY_2FA_ROLES
  const MANDATORY_2FA_ROLES = new Set(['super_admin', 'accountant'])

  const needsTwoFactorSetup = computed(
    () => !!user.value && MANDATORY_2FA_ROLES.has(role.value) && !user.value.two_factor_enabled,
  )
  const needsPasswordChange = computed(() => !!user.value?.must_change_password)

  // ── helpers ─────────────────────────────────────────────────────────────

  // نقطة واحدة لتغيير الـ token — يحدّث Pinia + axios.defaults في نفس الوقت
  // عشان كل request تاني (REST + WebSocket) يلاقي الـ token جاهز فوراً.
  function _setToken(t: string | null) {
    token.value = t
    setApiToken(t)
  }

  // CX-02C — clears bootstrap state on identity/session transitions.
  function _clearBootstrap() {
    activeBranchId.value = null
    allowedBranchIds.value = []
    effectivePermissions.value = []
    requiresBranchSelection.value = false
  }

  function _applyBootstrap(data: BootstrapData) {
    // contract_version check: fail gracefully on unknown future shapes.
    if (data.contract_version !== 1) {
      console.warn('[auth] Unknown bootstrap contract_version:', data.contract_version)
    }
    user.value = data.user
    activeBranchId.value = data.active_branch_id
    allowedBranchIds.value = data.allowed_branch_ids ?? []
    effectivePermissions.value = data.effective_permissions ?? []
    requiresBranchSelection.value = data.requires_branch_selection ?? false
  }

  async function fetchUser() {
    if (!token.value) return
    const res = await api.get(ENDPOINTS.auth.me)
    user.value = res.data
  }

  // CX-02C — primary post-login/post-refresh bootstrap. Fetches session
  // context (active branch, allowed branches, effective permissions) from
  // GET /auth/bootstrap. Must be called after every token acquisition.
  // Failures are rethrown so callers can decide whether to redirect to /login.
  async function fetchBootstrap(): Promise<void> {
    if (!token.value) return
    const res = await api.get(ENDPOINTS.auth.bootstrap)
    _applyBootstrap(res.data as BootstrapData)
  }

  // CX-02C — switch the active branch for this refresh family.
  // Persisted server-side on the refresh token row — survives page reload.
  // Returns the updated bootstrap data so callers can react to the new context.
  async function switchActiveBranch(branchId: number): Promise<void> {
    await api.put(ENDPOINTS.auth.activeBranch, { branch_id: branchId })
    // Re-fetch full bootstrap to get updated effective_permissions for the
    // new branch. A stale permission set would silently pass UI guards.
    await fetchBootstrap()
  }

  // Gate 3A — persist the signed-in user's own display language server-side.
  // The backend enforces the staff `ar|en` allow-list and ownership (target is
  // the token's user). We update local state from the server response so
  // `user.preferred_language` stays the single source of truth. The caller
  // (staff app) is responsible for applying the locale to the UI, and for
  // surfacing/rolling back on failure — this action rethrows on error rather
  // than pretending success.
  async function updatePreferredLanguage(language: string): Promise<string> {
    const res = await api.patch(ENDPOINTS.auth.mePreferences, {
      preferred_language: language,
    })
    user.value = res.data
    return res.data.preferred_language as string
  }

  // ── Public actions ───────────────────────────────────────────────────────

  async function login(
    username: string,
    password: string,
    otpCode?: string,
    recoveryCode?: string,
    enrollmentToken?: string,
  ) {
    isLoading.value = true
    try {
      const form = new URLSearchParams()
      form.append('username', username.trim())
      form.append('password', password.trim())
      if (otpCode) form.append('otp_code', otpCode.trim())
      if (recoveryCode) form.append('recovery_code', recoveryCode.trim())
      if (enrollmentToken) form.append('enrollment_token', enrollmentToken.trim())
      const res = await api.post(ENDPOINTS.auth.login, form, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        withCredentials: true,
      })
      await clearIdentityBoundClientState()
      _clearBootstrap()
      _setToken(res.data.access_token)
      pendingEnrollmentToken.value = enrollmentToken?.trim() ?? ''
      // CX-02C: bootstrap replaces the old fetchUser() call — it returns the
      // user record plus branch context in one shot (Cache-Control: no-store).
      await fetchBootstrap()
    } finally {
      isLoading.value = false
    }
  }

  // T-01: يُستدعى عند app init (main.ts) — يجدّد access_token من httpOnly cookie.
  // لو ما فيش cookie صالح يرجع false والـ router guard بيودّي /login.
  async function initAuth(): Promise<boolean> {
    try {
      const res = await api.post(ENDPOINTS.auth.refresh, {}, { withCredentials: true })
      await clearIdentityBoundClientState()
      _clearBootstrap()
      _setToken(res.data.access_token)
      // CX-02C: single bootstrap call after token refresh — replaces
      // the separate fetchUser() + branch-guessing that was here before.
      await fetchBootstrap()
      return true
    } catch {
      _setToken(null)
      user.value = null
      pendingEnrollmentToken.value = ''
      _clearBootstrap()
      return false
    }
  }

  // تبديل هوية المشغّل على جهاز كاشير (pin switch)
  async function pinSwitch(targetUserId: number, pin: string) {
    isLoading.value = true
    try {
      const res = await api.post(ENDPOINTS.core.pinSwitch, { user_id: targetUserId, pin })
      await clearIdentityBoundClientState()
      _clearBootstrap()
      _setToken(res.data.access_token)
      user.value = res.data.user
      // CX-02C: PIN switch carries a signed `bid` — re-bootstrap to pick up
      // the new branch context (backend validates membership and rejects
      // cross-branch switches with PIN_BRANCH_MISMATCH before we reach here).
      await fetchBootstrap()
    } finally {
      isLoading.value = false
    }
  }

  async function logout() {
    // لازم نستنى رد السيرفر قبل تغيير الصفحة؛ التنقل الفوري كان ممكن يقطع
    // طلب الـlogout ويترك refresh session صالحة على السيرفر رغم إن الواجهة
    // بدت للمستخدم كأنها خرجت. الفشل الشبكي لا يمنع التنظيف المحلي.
    const accessToken = token.value ?? ''
    try {
      await api.post(
        ENDPOINTS.auth.logout,
        { token: accessToken },
        { withCredentials: true, timeout: 5_000 },
      )
    } catch {
      // Offline/server failure: local credentials still must disappear.
    } finally {
      await clearIdentityBoundClientState()
      _setToken(null)
      user.value = null
      pendingEnrollmentToken.value = ''
      _clearBootstrap()
      window.location.replace('/login')
    }
  }

  return {
    user, token, isAuthenticated, role, branchId, isLoading,
    // CX-02C — branch context from bootstrap (session-scoped, no ?? 1 fallback)
    activeBranchId, allowedBranchIds, effectivePermissions, requiresBranchSelection,
    pendingEnrollmentToken,
    login, logout, fetchUser, fetchBootstrap, switchActiveBranch, initAuth,
    hasRole, hasPermission, roleLevel,
    needsTwoFactorSetup, needsPasswordChange, pinSwitch,
    updatePreferredLanguage,
  }
})
