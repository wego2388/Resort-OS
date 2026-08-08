import { api } from '@resort-os/core';
/**
 * owner API client — wraps Phase 3 + 6 + 7 + 7a endpoints.
 * Cache-Control: no-store set server-side — we never cache here either.
 */
export async function fetchOwnerNow() {
    const res = await api.get('/api/v1/owner/now');
    return res.data;
}
export async function fetchCreditReceivables() {
    const res = await api.get('/api/v1/owner/credit-receivables');
    return res.data;
}
export async function fetchOwnerNowHistory(days = 7) {
    const res = await api.get('/api/v1/owner/now/history', { params: { days } });
    return res.data;
}
export async function fetchOwnerPerformance() {
    const res = await api.get('/api/v1/owner/performance');
    return res.data;
}
export async function fetchSalesPerformance(params) {
    const res = await api.get('/api/v1/owner/sales', { params });
    return res.data;
}
export async function fetchBeachPerformance(params) {
    const res = await api.get('/api/v1/owner/beach-performance', { params });
    return res.data;
}
export async function fetchChannelAnalytics(params) {
    const res = await api.get('/api/v1/owner/channel-analytics', { params });
    return res.data;
}
export async function fetchExpenseAnalytics(params) {
    const res = await api.get('/api/v1/owner/expense-analytics', { params });
    return res.data;
}
export async function fetchProcurementAnalytics(params) {
    const res = await api.get('/api/v1/owner/procurement-analytics', { params });
    return res.data;
}
export async function fetchShiftMonitor() {
    const res = await api.get('/api/v1/owner/shifts');
    return res.data;
}
export async function fetchExceptions() {
    const res = await api.get('/api/v1/owner/exceptions');
    return res.data;
}
export async function fetchShiftHistory(days = 7) {
    const res = await api.get('/api/v1/owner/shifts/history', { params: { days } });
    return res.data;
}
export async function fetchHRSummary() {
    const res = await api.get('/api/v1/owner/hr-summary');
    return res.data;
}
export async function fetchDiscountAnalytics(params) {
    const res = await api.get('/api/v1/owner/discount-analytics', { params });
    return res.data;
}
