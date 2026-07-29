import { describe, expect, it } from 'vitest'
import {
  isOfflineRecordInScope,
  isOfflineRecordOwnedBy,
} from '@resort-os/core/composables'

describe('offline queue identity isolation', () => {
  it('only exposes a queued record to its creator', () => {
    expect(isOfflineRecordOwnedBy({ ownerUserId: 17 }, 17)).toBe(true)
    expect(isOfflineRecordOwnedBy({ ownerUserId: 17 }, 23)).toBe(false)
  })

  it('quarantines legacy records with no owner', () => {
    expect(isOfflineRecordOwnedBy({ ownerUserId: null }, 17)).toBe(false)
  })

  it('exposes nothing without an authenticated employee', () => {
    expect(isOfflineRecordOwnedBy({ ownerUserId: 17 }, null)).toBe(false)
    expect(isOfflineRecordOwnedBy({ ownerUserId: 17 }, undefined)).toBe(false)
  })

  it('requires the same creator, branch, and module', () => {
    const record = { ownerUserId: 17, branchId: 4, module: 'dining' as const }

    expect(isOfflineRecordInScope(record, 17, 4, 'dining')).toBe(true)
    expect(isOfflineRecordInScope(record, 23, 4, 'dining')).toBe(false)
    expect(isOfflineRecordInScope(record, 17, 9, 'dining')).toBe(false)
    expect(isOfflineRecordInScope(record, 17, 4, 'beach')).toBe(false)
    expect(isOfflineRecordInScope(record, 17, null, 'dining')).toBe(false)
  })
})
