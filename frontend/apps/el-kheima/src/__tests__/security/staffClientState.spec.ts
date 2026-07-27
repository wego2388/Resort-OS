import { describe, expect, it } from 'vitest'
import { isLegacyStaffApiCache } from '@/security/staffClientState'

describe('staff PWA cache cleanup', () => {
  it.each([
    'pos-menu-cache',
    'waiter-menu-cache',
    'kds-cache',
    'ops-api-cache',
  ])('recognizes legacy API cache %s', (cacheName) => {
    expect(isLegacyStaffApiCache(cacheName)).toBe(true)
  })

  it('does not delete the current static precache', () => {
    expect(isLegacyStaffApiCache('workbox-precache-v2-http://localhost:3001/')).toBe(false)
  })
})

