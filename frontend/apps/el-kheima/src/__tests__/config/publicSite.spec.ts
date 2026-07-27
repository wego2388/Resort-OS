import { describe, expect, it } from 'vitest'
import { resolvePublicSiteUrl } from '@/config/publicSite'

const localLocation = {
  protocol: 'http:',
  hostname: 'localhost',
} as Pick<Location, 'protocol' | 'hostname'>

describe('public site URL resolution', () => {
  it('normalizes the configured public URL', () => {
    expect(resolvePublicSiteUrl('https://guest.example.com///', localLocation, true))
      .toBe('https://guest.example.com')
  })

  it('rejects an insecure non-local public URL', () => {
    expect(() => resolvePublicSiteUrl('http://guest.example.com', localLocation, true))
      .toThrow(/https/)
  })

  it('rejects credentials, query strings, and fragments', () => {
    expect(() => resolvePublicSiteUrl('https://user:pass@example.com', localLocation, true))
      .toThrow(/credentials/)
    expect(() => resolvePublicSiteUrl('https://example.com?branch=1', localLocation, true))
      .toThrow(/query/)
    expect(() => resolvePublicSiteUrl('https://example.com/#guest', localLocation, true))
      .toThrow(/fragment/)
  })

  it('fails closed when production has no explicit public URL', () => {
    expect(() => resolvePublicSiteUrl(undefined, localLocation, true))
      .toThrow(/required/)
  })

  it('uses the public dev port on the same host during development', () => {
    expect(resolvePublicSiteUrl(undefined, localLocation, false))
      .toBe('http://localhost:5174')
  })
})

