/**
 * Gate 3C — router smoke: reference routes resolve, role landing map is
 * correct, and the auth guard redirects unauthenticated users to /login.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from '@resort-os/core'
import type { User } from '@resort-os/core'
import router, { homeRouteFor } from '../../router'

function authenticatedReceptionist(auth: ReturnType<typeof useAuthStore>) {
  auth.token = 'test-token'
  auth.user = {
    id: 91,
    username: 'router-test',
    email: 'router-test@example.invalid',
    full_name: 'Router Test',
    role: 'receptionist',
    branch_id: 1,
  } satisfies User
}

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('homeRouteFor — role landing map', () => {
  it.each([
    ['waiter', '/pos/dining'],
    ['chef', '/kds/dining'],
    ['cashier', '/pos/beach'],
    ['receptionist', '/ops/reception'],
    ['manager', '/admin/dashboard'],
    ['super_admin', '/admin/dashboard'],
    ['timeshare_admin', '/admin/timeshare'],
    ['timeshare_agent', '/admin/timeshare'],
  ])('routes %s to %s', (role, expected) => {
    expect(homeRouteFor(role)).toBe(expected)
  })
})

describe('reference routes are registered', () => {
  it.each([
    '/login',
    '/admin/settings',
    '/admin/permissions',
    '/admin/users',
    '/account/sessions',
    '/portal/profile',
    '/pos/dining',
    '/kds/dining',
  ])('resolves %s to a matched route', (path) => {
    const resolved = router.resolve(path)
    expect(resolved.matched.length).toBeGreaterThan(0)
    expect(resolved.name).not.toBe('not-found')
  })

  it.each([
    ['/admin/users', 'users'],
    ['/admin/permissions', 'permissions'],
  ])('keeps legacy %s bookmarks but redirects into the unified control center', async (path, tab) => {
    const resolved = router.resolve(path)
    const redirect = resolved.matched[resolved.matched.length - 1]?.redirect
    expect(redirect).toBeTruthy()
    const destination = typeof redirect === 'function'
      ? redirect(resolved as any, resolved as any)
      : redirect
    expect(destination).toMatchObject({
      path: '/admin/super-admin',
      query: { tab },
    })
  })
})

describe('auth guard', () => {
  it('redirects an unauthenticated user from a protected route to /login', async () => {
    const auth = useAuthStore()
    expect(auth.isAuthenticated).toBe(false)
    await router.push('/admin/settings')
    await router.isReady()
    expect(router.currentRoute.value.path).toBe('/login')
  })

  it('allows /login while unauthenticated', async () => {
    await router.push('/login')
    await router.isReady()
    expect(router.currentRoute.value.path).toBe('/login')
  })

  it('redirects operational routes to the fail-closed branch screen', async () => {
    const auth = useAuthStore()
    authenticatedReceptionist(auth)

    await router.push('/ops/rooms')
    expect(router.currentRoute.value.path).toBe('/select-branch')
  })

  it('redirects a branch user without the route permission', async () => {
    const auth = useAuthStore()
    authenticatedReceptionist(auth)
    auth.activeBranchId = 1

    await router.push('/ops/rooms')
    expect(router.currentRoute.value.path).toBe('/portal/profile')
  })

  it('allows a branch user with the server-evaluated route permission', async () => {
    const auth = useAuthStore()
    authenticatedReceptionist(auth)
    auth.activeBranchId = 1
    auth.effectivePermissions = [{
      resource: 'pms.rooms',
      action: 'view',
      label_ar: 'عرض الغرف',
      module: 'pms',
      allowed: true,
      source: 'role',
    }]

    await router.push('/ops/rooms')
    expect(router.currentRoute.value.path).toBe('/ops/rooms')
  })
})
