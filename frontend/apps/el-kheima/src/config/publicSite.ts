const LOOPBACK_HOSTS = new Set(['localhost', '127.0.0.1', '[::1]'])

function normalizeConfiguredUrl(value: string): string {
  const parsed = new URL(value)

  if (!['http:', 'https:'].includes(parsed.protocol)) {
    throw new Error('VITE_PUBLIC_SITE_URL must use http or https')
  }
  if (parsed.username || parsed.password || parsed.search || parsed.hash) {
    throw new Error('VITE_PUBLIC_SITE_URL must not contain credentials, a query, or a fragment')
  }
  if (parsed.protocol !== 'https:' && !LOOPBACK_HOSTS.has(parsed.hostname)) {
    throw new Error('VITE_PUBLIC_SITE_URL must use https outside local development')
  }

  return parsed.toString().replace(/\/+$/, '')
}

/**
 * Resolve the guest-facing origin embedded in physical QR codes.
 *
 * Production must always provide an explicit URL. Development keeps a
 * predictable same-host fallback so a phone on the local network can open the
 * public Vite app without inheriting the staff app's port.
 */
export function resolvePublicSiteUrl(
  configuredValue: string | undefined,
  currentLocation: Pick<Location, 'protocol' | 'hostname'>,
  isProduction: boolean,
): string {
  const configured = configuredValue?.trim()
  if (configured) return normalizeConfiguredUrl(configured)

  if (isProduction) {
    throw new Error('VITE_PUBLIC_SITE_URL is required for production QR codes')
  }

  const hostname = currentLocation.hostname.includes(':')
    ? `[${currentLocation.hostname.replace(/^\[|\]$/g, '')}]`
    : currentLocation.hostname
  return `${currentLocation.protocol}//${hostname}:5174`
}

