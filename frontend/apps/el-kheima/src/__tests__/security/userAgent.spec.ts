/**
 * OPS-DATA-02 UX-API-01 §6.6 — parseUserAgent turns the raw User-Agent
 * string stored on RefreshToken (and shown on the Sessions/security
 * activity screens) into "Browser · OS" instead of the raw string.
 */
import { describe, it, expect } from 'vitest'
import { parseUserAgent } from '@resort-os/core'

describe('parseUserAgent', () => {
  it('parses a Chrome-on-Windows desktop UA', () => {
    const ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      + '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    expect(parseUserAgent(ua)).toBe('Chrome · Windows 10/11')
  })

  it('parses a Safari-on-iOS mobile UA', () => {
    const ua = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) '
      + 'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'
    expect(parseUserAgent(ua)).toBe('Safari · iOS')
  })

  it('parses a Firefox-on-Linux UA', () => {
    const ua = 'Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0'
    expect(parseUserAgent(ua)).toBe('Firefox · Linux')
  })

  it('falls back to whichever half is recognized', () => {
    expect(parseUserAgent('SomeCustomClient/1.0 (Android 14)')).toBe('Android')
  })

  it('returns null for empty/unrecognized input, not an empty string', () => {
    expect(parseUserAgent(null)).toBeNull()
    expect(parseUserAgent('')).toBeNull()
    expect(parseUserAgent('   ')).toBeNull()
    expect(parseUserAgent('totally-unknown-client')).toBeNull()
  })
})
