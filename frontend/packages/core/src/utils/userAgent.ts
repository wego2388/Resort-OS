// OPS-DATA-02 UX-API-01 §6.6 — session/security-activity screens used to
// render the raw User-Agent string (e.g. "Mozilla/5.0 (Windows NT 10.0;
// Win64; x64) AppleWebKit/537.36 ... Chrome/120.0.0.0 Safari/537.36")
// straight from the backend (auth/service.py's `device` field is literally
// `RefreshToken.user_agent`, unparsed). Not human-friendly in any locale,
// and doubly awkward mixed into an RTL layout. This does light,
// dependency-free parsing into "Browser on OS" — good enough for a staff
// security screen, not meant to be a full UA-sniffing library.

const BROWSER_PATTERNS: Array<[RegExp, string]> = [
  [/edg\//i, 'Edge'],
  [/opr\/|opera/i, 'Opera'],
  [/chrome\//i, 'Chrome'],
  [/crios\//i, 'Chrome'],
  [/fxios\//i, 'Firefox'],
  [/firefox\//i, 'Firefox'],
  [/version\/.*safari/i, 'Safari'],
  [/safari\//i, 'Safari'],
]

const OS_PATTERNS: Array<[RegExp, string]> = [
  [/windows nt 10/i, 'Windows 10/11'],
  [/windows nt/i, 'Windows'],
  // iOS UAs contain the literal substring "like Mac OS X" (a long-standing
  // UA quirk for compatibility) — must be checked before the macOS pattern
  // or every iPhone/iPad UA misparses as a Mac.
  [/iphone|ipad|ipod/i, 'iOS'],
  [/mac os x/i, 'macOS'],
  [/android/i, 'Android'],
  [/linux/i, 'Linux'],
]

function firstMatch(ua: string, patterns: Array<[RegExp, string]>): string | null {
  for (const [pattern, label] of patterns) {
    if (pattern.test(ua)) return label
  }
  return null
}

/** Parses a raw User-Agent string into "Browser on OS" (or whichever half
 * is actually recognized). Returns null for empty/unrecognized input so
 * callers can fall back to their own "unknown device" copy. */
export function parseUserAgent(userAgent: string | null | undefined): string | null {
  const ua = (userAgent ?? '').trim()
  if (!ua) return null
  const browser = firstMatch(ua, BROWSER_PATTERNS)
  const os = firstMatch(ua, OS_PATTERNS)
  if (browser && os) return `${browser} · ${os}`
  return browser ?? os
}
