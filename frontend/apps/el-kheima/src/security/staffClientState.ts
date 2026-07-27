/**
 * Runtime API caches created by older staff PWA releases.
 *
 * Current releases precache static application assets only. These names stay
 * here so an upgraded browser cannot keep serving guest, booking, stock, or
 * shift data cached by a previous service worker.
 */
export const LEGACY_STAFF_API_CACHE_NAMES = new Set([
  'pos-menu-cache',
  'waiter-menu-cache',
  'kds-cache',
  'ops-api-cache',
])

export function isLegacyStaffApiCache(cacheName: string): boolean {
  return LEGACY_STAFF_API_CACHE_NAMES.has(cacheName)
}

export async function clearLegacyStaffApiCaches(): Promise<void> {
  if (!('caches' in globalThis)) return

  const cacheNames = await globalThis.caches.keys()
  await Promise.all(
    cacheNames
      .filter(isLegacyStaffApiCache)
      .map(cacheName => globalThis.caches.delete(cacheName)),
  )
}

