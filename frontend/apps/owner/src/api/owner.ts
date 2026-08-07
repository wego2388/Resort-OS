import { api } from '@resort-os/core'
import type { OwnerNowResponse, OwnerPerformanceResponse } from './types'

/**
 * owner API client — wraps the two Phase 3 endpoints.
 * Cache-Control: no-store set server-side — we never cache here either.
 */
export async function fetchOwnerNow(): Promise<OwnerNowResponse> {
  const res = await api.get<OwnerNowResponse>('/api/v1/owner/now')
  return res.data
}

export async function fetchOwnerPerformance(): Promise<OwnerPerformanceResponse> {
  const res = await api.get<OwnerPerformanceResponse>('/api/v1/owner/performance')
  return res.data
}
