import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from '@resort-os/core'
import type { User } from '@resort-os/core'

function userWithRole(role: string): User {
  return {
    id: 7,
    username: 'role-test',
    email: 'role-test@example.invalid',
    full_name: 'Role Test',
    role,
    branch_id: 1,
  }
}

describe('frontend role guard', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('recognizes the backend timeshare_agent level', () => {
    const auth = useAuthStore()
    auth.user = userWithRole('timeshare_agent')

    expect(auth.hasRole('employee')).toBe(true)
    expect(auth.hasRole('waiter')).toBe(false)
    expect(auth.roleLevel).toBe(25)
  })

  it('fails closed for an unknown authenticated role', () => {
    const auth = useAuthStore()
    auth.user = userWithRole('misspelled_role')

    expect(auth.hasRole('guest')).toBe(false)
    expect(auth.roleLevel).toBe(-1)
  })

  it('fails closed for an unknown minimum-role requirement', () => {
    const auth = useAuthStore()
    auth.user = userWithRole('super_admin')

    expect(auth.hasRole('misspelled_requirement')).toBe(false)
  })

  it('uses allowed permission objects from the active branch bootstrap', () => {
    const auth = useAuthStore()
    auth.user = userWithRole('receptionist')
    auth.activeBranchId = 3
    auth.effectivePermissions = [
      {
        resource: 'pms.bookings',
        action: 'view',
        label_ar: 'عرض الحجوزات',
        module: 'pms',
        allowed: true,
        source: 'role',
      },
      {
        resource: 'pms.bookings',
        action: 'create',
        label_ar: 'إنشاء حجز',
        module: 'pms',
        allowed: false,
        source: 'explicit',
      },
    ]

    expect(auth.hasPermission('pms.bookings:view')).toBe(true)
    expect(auth.hasPermission('pms.bookings:create')).toBe(false)
    expect(auth.hasPermission('pms.bookings:check_in')).toBe(false)
  })

  it('fails permission checks without an active branch', () => {
    const auth = useAuthStore()
    auth.effectivePermissions = [{
      resource: 'pms.rooms',
      action: 'view',
      label_ar: 'عرض الغرف',
      module: 'pms',
      allowed: true,
      source: 'role',
    }]

    expect(auth.hasPermission('pms.rooms:view')).toBe(false)
  })
})
