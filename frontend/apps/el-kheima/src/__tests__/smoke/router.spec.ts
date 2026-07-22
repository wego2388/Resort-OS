/**
 * Gate 3C — router smoke: reference routes resolve, role landing map is
 * correct, and the auth guard redirects unauthenticated users to /login.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from '@resort-os/core'
import router, { homeRouteFor } from '../../router'

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
})
