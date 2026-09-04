import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, refreshAccessToken, setApiToken } from '@resort-os/core/api'

describe('refresh token rotation coordination', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    setApiToken(null)
  })

  it('deduplicates concurrent callers and enters the browser-wide lock once', async () => {
    let resolveRequest: ((value: { data: { access_token: string } }) => void) | undefined
    const request = new Promise<{ data: { access_token: string } }>((resolve) => {
      resolveRequest = resolve
    })
    const post = vi.spyOn(api, 'post').mockReturnValue(request as never)
    const lockRequest = vi.fn(async (
      _name: string,
      _options: LockOptions,
      callback: () => Promise<string>,
    ) => callback())
    Object.defineProperty(navigator, 'locks', {
      configurable: true,
      value: { request: lockRequest },
    })

    const first = refreshAccessToken()
    const second = refreshAccessToken()
    resolveRequest?.({ data: { access_token: 'rotated-once' } })

    await expect(Promise.all([first, second])).resolves.toEqual([
      'rotated-once',
      'rotated-once',
    ])
    expect(post).toHaveBeenCalledTimes(1)
    expect(lockRequest).toHaveBeenCalledTimes(1)
  })
})
