import { api } from '@resort-os/core';
/**
 * owner API client — wraps the two Phase 3 endpoints.
 * Cache-Control: no-store set server-side — we never cache here either.
 */
export async function fetchOwnerNow() {
    const res = await api.get('/api/v1/owner/now');
    return res.data;
}
export async function fetchOwnerPerformance() {
    const res = await api.get('/api/v1/owner/performance');
    return res.data;
}
