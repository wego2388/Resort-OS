import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '../api/client'
import { ENDPOINTS } from '../api/endpoints'
import type { User } from '../types'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const token = ref<string | null>(localStorage.getItem('access_token'))
  const isLoading = ref(false)

  const isAuthenticated = computed(() => !!token.value && !!user.value)
  const role = computed(() => user.value?.role ?? '')
  const branchId = computed(() => user.value?.branch_id ?? 1)

  // Mirrors backend ROLE_LEVELS (app/core/deps.py) — numeric so roles that share
  // a level (e.g. cashier/receptionist, waiter/chef/kitchen) compare correctly.
  // An array-indexOf hierarchy can't express two roles at the same level, which
  // is exactly what broke silently before this was ever exercised by a router guard.
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

  // Mirrors backend app/core/deps.py::MANDATORY_2FA_ROLES exactly (same
  // duplication pattern as ROLE_LEVELS above — see CLAUDE.md § 14 rule 5).
  // Every request from these roles gets a 403 `2FA_REQUIRED` from the backend
  // until two_factor_enabled is true; before this the frontend had zero
  // awareness of that gate, so a super_admin/accountant without 2FA set up
  // just saw every screen silently render empty/zeroed data.
  const MANDATORY_2FA_ROLES = new Set(['super_admin', 'accountant'])

  const needsTwoFactorSetup = computed(
    () => !!user.value && MANDATORY_2FA_ROLES.has(role.value) && !user.value.two_factor_enabled,
  )

  async function login(username: string, password: string) {
    isLoading.value = true
    const form = new URLSearchParams()
    form.append('username', username)
    form.append('password', password)
    const res = await api.post(ENDPOINTS.auth.login, form, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })
    token.value = res.data.access_token
    localStorage.setItem('access_token', token.value!)
    await fetchUser()
    isLoading.value = false
  }

  async function fetchUser() {
    if (!token.value) return
    const res = await api.get(ENDPOINTS.auth.me)
    user.value = res.data
  }

  function logout() {
    user.value = null
    token.value = null
    localStorage.removeItem('access_token')
  }

  return { user, token, isAuthenticated, role, branchId, isLoading, login, logout, fetchUser, hasRole, needsTwoFactorSetup }
})
